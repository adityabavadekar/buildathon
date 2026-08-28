@AGENTS.md

## Claude-specific notes

- Run `make check` before reporting a change complete. Report failures with the
  actual output rather than describing them.
- The `money rules` section in AGENTS.md is the part most easily got wrong from
  general priors. Re-read it before touching anything that handles an amount.
- When research is needed on Razorpay's API surface or India's payments
  regulation, check `docs/RESEARCH.md` first — it is already verified, with
  claims tagged by confidence, and includes findings that contradict common
  assumptions.
