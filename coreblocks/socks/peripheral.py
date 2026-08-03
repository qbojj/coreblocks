from amaranth import *
from amaranth.utils import ceil_log2
from amaranth_types import ModuleLike
from amaranth.lib import wiring
from typing import Protocol

from coreblocks.peripherals.wishbone import WishboneInterface, WishboneMuxer, WishboneParameters


class SocksPeripheral(Protocol):
    bus: WishboneInterface
    base_addr: int
    addr_space_size: int


def convert_to_wishbone_addr(bus: WishboneInterface, byte_addr: int):
    # Convert from byte-addressed to word addresed wishbone address
    word_width = bus.dat_r.shape().width
    drop_addr_bits = ceil_log2(word_width // 8)
    wishbone_addr = byte_addr >> drop_addr_bits
    if byte_addr & ((1 << drop_addr_bits) - 1):
        raise ValueError(f"Register base address must be aligned to bus word ({word_width // 8} bytes)")
    return wishbone_addr


def bus_in_periph_range(bus: WishboneInterface, periph: SocksPeripheral):
    return (bus.adr >= convert_to_wishbone_addr(bus, periph.base_addr)) & (
        bus.adr <= convert_to_wishbone_addr(bus, periph.base_addr + periph.addr_space_size)
    )


def is_peripheral_request(periph: SocksPeripheral):
    return periph.bus.cyc & periph.bus.stb & bus_in_periph_range(periph.bus, periph)


def gen_memory_mapped_register(
    m: ModuleLike, periph: SocksPeripheral, addr_offset: int, register: Signal, read_only: bool = False
):
    bus = periph.bus

    reg_width = register.shape().width
    word_width = bus.dat_r.shape().width
    words_in_reg = (reg_width + word_width - 1) // word_width

    wishbone_addr = convert_to_wishbone_addr(bus, periph.base_addr + addr_offset)

    with m.If(bus.stb & bus.cyc):
        for word in range(words_in_reg):
            with m.If(bus.adr == wishbone_addr + word):
                reg_slice = register[word * word_width : min(reg_width, (word + 1) * word_width)]

                m.d.comb += bus.dat_r.eq(reg_slice)
                m.d.comb += bus.ack.eq(1)
                m.d.comb += bus.err.eq(0)

                with m.If(bus.we):
                    if read_only:
                        m.d.comb += bus.ack.eq(0)
                        m.d.comb += bus.err.eq(1)
                    else:
                        if bus.sel.shape().width:
                            sel_mask_bits = word_width // bus.sel.shape().width
                            write_mask = Cat(
                                [bus.sel[i].replicate(sel_mask_bits) for i in range(bus.sel.shape().width)]
                            )
                        else:
                            write_mask = -1

                        m.d.sync += reg_slice.eq((bus.dat_w & write_mask) | (reg_slice & ~write_mask))


def make_peripheral_muxer(
    m: Module, wb_params: WishboneParameters, peripherals: list[SocksPeripheral]
) -> WishboneMuxer:
    """Create WishboneMuxer that captures all peripheral requests and routes them to the correct peripheral.
    master_wb and slaves[0] of the muxer are left to be connected by the caller.
    """
    ssel_tga = Signal(1 + len(peripherals))
    muxer = WishboneMuxer(wb_params, ssel_tga)
    for i, periph in enumerate(peripherals, 1):
        m.d.comb += ssel_tga[i].eq(bus_in_periph_range(muxer.master_wb, periph))
        wiring.connect(m, muxer.slaves[i], periph.bus)
    m.d.comb += ssel_tga[0].eq(~ssel_tga[1:].any())
    return muxer
