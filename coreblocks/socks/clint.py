from amaranth import *
from amaranth.lib.wiring import Component, In, Out

from dataclasses import dataclass

from transactron.lib.dependencies import SimpleKey

from coreblocks.peripherals.wishbone import WishboneInterface, WishboneParameters
from coreblocks.socks.peripheral import SocksPeripheral, gen_memory_mapped_register, is_peripheral_request


MAX_HARTS_PER_DEVICE = 4095


@dataclass(frozen=True)
class ClintMtimeKey(SimpleKey[Value]):
    pass


class AclintMtimer(Component, SocksPeripheral):
    """MTIMER ACLINT compliant device"""

    bus: WishboneInterface
    mtip: Signal
    mtime: Signal

    def __init__(self, base_addr: int, *, wb_params: WishboneParameters, hart_count: int = 1):
        super().__init__(
            {
                "bus": In(WishboneInterface(wb_params).signature),
                "mtip": Out(hart_count),
                "mtime": Out(64),
            }
        )

        self.hart_count = hart_count
        self.base_addr = base_addr
        self.addr_space_size = 0x8000
        assert hart_count <= MAX_HARTS_PER_DEVICE

    def elaborate(self, platform):
        m = Module()

        m.d.sync += self.mtime.eq(self.mtime + 1)
        mtimecmp = [Signal(64) for _ in range(self.hart_count)]
        for i in range(self.hart_count):
            m.d.comb += self.mtip[i].eq(self.mtime >= mtimecmp[i])

        with m.If(is_peripheral_request(self)):
            m.d.comb += self.bus.err.eq(1)  # default - overwritten by memory mapped registers declaration
            m.d.comb += self.bus.ack.eq(0)

        for hart in range(self.hart_count):
            gen_memory_mapped_register(m, self, 8 * hart, mtimecmp[hart])

        gen_memory_mapped_register(m, self, self.addr_space_size - 8, self.mtime)
        return m


class AclintMswi(Component, SocksPeripheral):
    """MSWI ACLINT compliant device"""

    bus: WishboneInterface
    msip: Signal

    def __init__(self, base_addr: int, *, wb_params: WishboneParameters, hart_count: int = 1):
        super().__init__(
            {
                "bus": In(WishboneInterface(wb_params).signature),
                "msip": Out(hart_count),
            }
        )

        self.hart_count = hart_count
        self.base_addr = base_addr
        self.addr_space_size = 0x4000
        assert hart_count <= MAX_HARTS_PER_DEVICE

    def elaborate(self, platform):
        m = Module()

        ipi = [Signal() for _ in range(self.hart_count)]

        with m.If(is_peripheral_request(self)):
            m.d.comb += self.bus.err.eq(1)  # default - overwritten by memory mapped registers declaration
            m.d.comb += self.bus.ack.eq(0)

        for hart in range(self.hart_count):
            gen_memory_mapped_register(m, self, 4 * hart, ipi[hart])
            m.d.comb += self.msip[hart].eq(ipi[hart])

        return m


class AclintSswi(Component, SocksPeripheral):
    """SSWI ACLINT compliant device"""

    bus: WishboneInterface
    ssip: Signal

    def __init__(self, base_addr: int, *, wb_params: WishboneParameters, hart_count: int = 1):
        super().__init__(
            {
                "bus": In(WishboneInterface(wb_params).signature),
                "ssip": Out(hart_count),
            }
        )

        self.hart_count = hart_count
        self.base_addr = base_addr
        self.addr_space_size = 0x4000
        assert hart_count <= MAX_HARTS_PER_DEVICE

    def elaborate(self, platform):
        m = Module()

        ipi = [Signal() for _ in range(self.hart_count)]

        with m.If(is_peripheral_request(self)):
            m.d.comb += self.bus.err.eq(1)  # default - overwritten by memory mapped registers declaration
            m.d.comb += self.bus.ack.eq(0)

        for hart in range(self.hart_count):
            m.d.sync += ipi[hart].eq(0)
            gen_memory_mapped_register(m, self, 4 * hart, ipi[hart])
            # edge triggered
            m.d.comb += self.ssip[hart].eq(ipi[hart])

        return m
