# Court Decree Residual Duty Ledger

An Intelligent Contract that records a sealed federal consent decree and a later modification order, verifies the source digests, and returns paragraph-level outcomes without overwriting the historical order.

## Public verification

- Network: GenLayer Studio Dev (chain 61997)
- Contract: `0xAF83E0EEE7bdDe7981C1f58B94F5F2969C12DBe2`
- Source: [DOJ consent-decree page](https://www.justice.gov/crt/case-document/united-states-v-city-newark-consent-decree)
- Modification record: [DOJ Special Litigation case summaries](https://www.justice.gov/crt/special-litigation-section-case-summaries)
- Assessment readback: `ASSESSED_FINAL`, `VERIFIED`, granted, same case and decree.
- Paragraph 43: `TERMINATED`; paragraph 44: `SURVIVES_THIS_ORDER`.

The contract exposes public read methods for the decree, order, and residual-duty result. The source, tests, and verification artifacts in this repository are the complete judge-facing implementation.
