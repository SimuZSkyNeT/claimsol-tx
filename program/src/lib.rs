//! close_many: one instruction closes many token accounts of the signer.
//!
//! Accounts: [0] owner — signer, authority of every token account, and destination of the
//!                 rent (SOL goes back to the same wallet). Must be writable.
//!           [1] Tokenkeg program (readonly, executable)
//!           [2] Token-2022 program (readonly, executable)
//!           [3..] the token accounts to close, in any order (max ~56: the rest of the
//!                 64-account budget goes to owner + 2 token programs + this program + wallet
//!                 guards).
//! Data: empty. Nothing else can happen in this program: the only CPI is Token CloseAccount
//! (ix 9) with destination = authority = the signer, on Tokenkeg or Token-2022.
//!
//! Why it exists: Phantom blocks transactions with more than ~32 instructions, so the classic
//! flow packs at most 25 closures per transaction. With this program ONE instruction closes up
//! to ~56 accounts (Solana's hard limit is 64 accounts per transaction; a few slots are left
//! for the fee transfer and wallet-side guards), cutting approvals ~2x. It is the exact code
//! published for users to verify.

use solana_program::{
    account_info::{next_account_info, AccountInfo},
    entrypoint,
    entrypoint::ProgramResult,
    instruction::{AccountMeta, Instruction},
    program::invoke,
    program_error::ProgramError,
    pubkey::Pubkey,
};

entrypoint!(process_instruction);

const TOKENKEG: Pubkey = solana_program::pubkey!("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
const TOKEN22: Pubkey = solana_program::pubkey!("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");

pub fn process_instruction(
    _program_id: &Pubkey,
    accounts: &[AccountInfo],
    _data: &[u8],
) -> ProgramResult {
    let mut it = accounts.iter();
    let owner = next_account_info(&mut it)?; // signer: authority of every account + destination of the rent
    if !owner.is_signer {
        return Err(ProgramError::MissingRequiredSignature);
    }

    // invoke() needs the AccountInfo of the called program among the passed accounts:
    // that is why the two token programs are accounts of the instruction.
    let keg = next_account_info(&mut it)?;
    let t22 = next_account_info(&mut it)?;
    if keg.key != &TOKENKEG || t22.key != &TOKEN22 {
        return Err(ProgramError::IncorrectProgramId);
    }
    for p in [keg, t22] {
        if !p.executable {
            return Err(ProgramError::IncorrectProgramId);
        }
    }

    let mut n = 0usize;
    for acc in it {
        let tp = if *acc.owner == TOKENKEG {
            keg
        } else if *acc.owner == TOKEN22 {
            t22
        } else {
            return Err(ProgramError::IllegalOwner);
        };
        // SPL/T-2022 CloseAccount (ix 9): account writable, destination writable, authority signer.
        let ix = Instruction {
            program_id: *tp.key,
            accounts: vec![
                AccountMeta::new(*acc.key, false),
                AccountMeta::new(*owner.key, false),
                AccountMeta::new_readonly(*owner.key, true),
            ],
            data: vec![9],
        };
        invoke(&ix, &[acc.clone(), owner.clone(), owner.clone(), tp.clone()])?;
        n += 1;
    }
    if n == 0 {
        return Err(ProgramError::NotEnoughAccountKeys);
    }
    Ok(())
}
