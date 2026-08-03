from amaranth import *
from amaranth.lib.wiring import Component, In, Out, connect, flipped
from transactron.utils import DependencyContext

from coreblocks.arch.isa_consts import InterruptCauseNumber
from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.peripherals.wishbone import WishboneInterface
from coreblocks.priv.traps.interrupt_controller import ISA_RESERVED_INTERRUPTS
from coreblocks.socks.clint import AclintMtimer, AclintMswi, AclintSswi, ClintMtimeKey
from coreblocks.socks.peripheral import make_peripheral_muxer
from coreblocks.socks.plic import PlicPeriph

# CLINT is MSWI followed by MTIMER
CLINT_BASE = 0xE1000000
ACLINT_MSWI_BASE = CLINT_BASE + 0x0000
ACLINT_MTIMER_BASE = CLINT_BASE + 0x4000

ACLINT_SSWI_BASE = CLINT_BASE + 0xC000
PLIC_BASE = 0xE2000000

# This is a temporary wrapper solution to provide external memory-mapped components, required to run Linux.
# It is intended to be only usable with LiteX, that uses a simple core-facing interface and Wishbone bus
# (and is currenty the only supported integration).
# TODO: Replace this with a proper bus-agnostic (and multicore?) soultion at a later stage.


class Socks(Component):
    wb_instr: WishboneInterface
    wb_data: WishboneInterface

    interrupts: Signal
    """ Interrupts input signal
    If `with_plic` is set to True, then it's the input to the RISC-V Platform Level Interrupt Controller module.
    PLIC wires interrupts contexts 0 to MEI and 1 to SEI. Signal has width of `interrupt_custom_count +1`.
    Note that PLIC interrupt 0 is reserved and bit 0 is ignored.
    If `with_plic` is set to False, `interrupts` width is 16 (number of interrupts reserved by ISA) +
    `interrupt_custom_count` and interrupts are directly wired to Hart Local Interrupt Controller.
    In both cases MTI and MSI are ignored and provided from CLINT.
    """

    def __init__(self, core: Core, core_gen_params: GenParams, with_plic: bool = True, with_aclint_sswi: bool = True):
        super().__init__(
            {
                "wb_instr": Out(WishboneInterface(core_gen_params.wb_params).signature),
                "wb_data": Out(WishboneInterface(core_gen_params.wb_params).signature),
                "interrupts": In(
                    (1 if with_plic else ISA_RESERVED_INTERRUPTS) + core_gen_params.interrupt_custom_count
                ),
            }
        )

        self.aclint_mswi = AclintMswi(base_addr=ACLINT_MSWI_BASE, wb_params=core_gen_params.wb_params)
        self.aclint_mtimer = AclintMtimer(base_addr=ACLINT_MTIMER_BASE, wb_params=core_gen_params.wb_params)
        DependencyContext.get().add_dependency(ClintMtimeKey(), self.aclint_mtimer.mtime)

        if with_aclint_sswi:
            self.aclint_sswi = AclintSswi(base_addr=ACLINT_SSWI_BASE, wb_params=core_gen_params.wb_params)
        else:
            self.aclint_sswi = None

        if with_plic:
            self.plic = PlicPeriph(
                base_addr=PLIC_BASE,
                wb_params=core_gen_params.wb_params,
                interrupt_count=core_gen_params.interrupt_custom_count,
                context_count=2,
            )
        else:
            self.plic = None

        self.core = core
        self.core_gen_params = core_gen_params

    def elaborate(self, platform):
        m = Module()

        devices = [
            self.aclint_mswi,
            self.aclint_mtimer,
        ]
        if self.aclint_sswi:
            devices.append(self.aclint_sswi)
        if self.plic:
            devices.append(self.plic)

        m.submodules.periph_muxer = periph_muxer = make_peripheral_muxer(
            m,
            self.core_gen_params.wb_params,
            devices,
        )
        connect(m, self.core.wb_instr, flipped(self.wb_instr))
        connect(m, periph_muxer.master_wb, self.core.wb_data)
        connect(m, flipped(self.wb_data), periph_muxer.slaves[0])

        m.submodules.core = self.core

        if self.plic:
            m.d.comb += self.plic.interrupts.eq(self.interrupts)
            m.d.comb += self.core.interrupts[InterruptCauseNumber.MEI].eq(self.plic.eip[0])
            m.d.comb += self.core.interrupts[InterruptCauseNumber.SEI].eq(self.plic.eip[1])
        else:
            m.d.comb += self.core.interrupts[InterruptCauseNumber.MEI].eq(self.interrupts[InterruptCauseNumber.MEI])
            m.d.comb += self.core.interrupts[ISA_RESERVED_INTERRUPTS:].eq(self.interrupts[ISA_RESERVED_INTERRUPTS:])
        m.d.comb += self.core.interrupts[InterruptCauseNumber.MTI].eq(self.aclint_mtimer.mtip)
        m.d.comb += self.core.interrupts[InterruptCauseNumber.MSI].eq(self.aclint_mswi.msip)
        if self.aclint_sswi:
            m.d.comb += self.core.interrupts[InterruptCauseNumber.SSI].eq(self.aclint_sswi.ssip)

        return m
