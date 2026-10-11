"""Address Lookup Tables for Claim Sol (added 11/10/2026): more accounts per transaction, fewer approvals.

Phantom 26.x blocks requests that carry several transactions at once, so every transaction is one
approval. Without a table about 10 accounts fit in a transaction (32 bytes each); with a table each
account costs 1 byte. Measured limits: Solana allows 64 accounts per transaction, and Phantom blocks
transactions with more than ~32 instructions, so we put at most 25 token instructions in each.

The table is created and paid by OUR project wallet (authority = project): the user signs nothing
extra. It only lists the user's token accounts (and the mints of tokens being burned). After use it
is deactivated and closed, and the rent goes back to the project wallet.
"""
import struct

from solders.address_lookup_table_account import derive_lookup_table_address
from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

ALT = Pubkey.from_string("AddressLookupTab1e1111111111111111111111111")
SYS = Pubkey.from_string("11111111111111111111111111111111")
PER_EXTEND = 27            # addresses per extend instruction (keeps the tx under 1232 bytes)


def crea(autorita: Pubkey, pagatore: Pubkey, slot: int):
    """(instruction, table address)."""
    tab, bump = derive_lookup_table_address(autorita, slot)
    data = struct.pack("<IQB", 0, slot, bump)
    ix = Instruction(ALT, data, [AccountMeta(tab, False, True), AccountMeta(autorita, True, False),
                                 AccountMeta(pagatore, True, True), AccountMeta(SYS, False, False)])
    return ix, tab


def estendi(tab: Pubkey, autorita: Pubkey, pagatore: Pubkey, indirizzi):
    data = struct.pack("<IQ", 2, len(indirizzi)) + b"".join(bytes(a) for a in indirizzi)
    return Instruction(ALT, data, [AccountMeta(tab, False, True), AccountMeta(autorita, True, False),
                                   AccountMeta(pagatore, True, True), AccountMeta(SYS, False, False)])


def disattiva(tab: Pubkey, autorita: Pubkey):
    return Instruction(ALT, struct.pack("<I", 3), [AccountMeta(tab, False, True), AccountMeta(autorita, True, False)])


def chiudi(tab: Pubkey, autorita: Pubkey, destinatario: Pubkey):
    return Instruction(ALT, struct.pack("<I", 4), [AccountMeta(tab, False, True), AccountMeta(autorita, True, False),
                                                   AccountMeta(destinatario, False, True)])
