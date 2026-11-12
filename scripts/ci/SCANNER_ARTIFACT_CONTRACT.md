# Scanner artifact containment bounds

`artifact-confidentiality-scanner.mjs` checks supplied, non-empty credentials in
raw UTF-8 and UTF-16LE, and in standard or URL-safe base64 with or without
applicable padding. For each supplied credential it checks one through four
consecutive base64 layers, including mixed alphabets and padding. This exact,
sentinel-aware check covers short six-digit PINs without decoding every short
alphanumeric token in an HTML or JSON report.

The scanner also decodes recognized base64 payloads, ZIP entries and gzip
members recursively. Default traversal bounds are eight levels, 10,000 ZIP
entries, 64 MiB per decoded node, 256 MiB total decoded bytes, 2,000 generic
base64 candidates per node and a 1,000:1 ZIP compression ratio. A supplied
credential may be at most 4,096 UTF-8 bytes; at most 1,024 exact encoding forms
are generated for it. Exceeding an inspection budget, or encountering malformed,
encrypted or unsupported archive content, fails the scan.

The four-layer exact check is a declared bound. It does not claim to recognize
arbitrary custom encodings or an unlimited number of base64 layers. The generic
base64 traversal retains its 32-character unmarked-token threshold; shorter
unmarked strings are checked through the supplied credential's bounded forms.
