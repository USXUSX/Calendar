# Samples

`synthetic-trip.json` is the non-sensitive complete trip used by the read-only
prototype. It is deliberately fictional and must not be replaced with private
or production travel data.

The sample conforms to `Schemas/trip.schema.json` and is validated by
`scripts/validate_trip.py`. Its explicit `null` values and empty arrays are part
of the ChatGPT generation contract, not compatibility placeholders.

Only synthetic, non-sensitive examples that are safe to commit belong here. Real household, account, or runtime data belongs in `/Users/us/Tools/LocalData/Calendar_Local`.
