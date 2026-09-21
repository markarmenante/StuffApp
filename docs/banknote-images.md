# Banknote images: Check preserves the displayed crops

Banknote images are cropped once when uploaded (or acquired through Market
Buy/Bought). The displayed crop, original holder photo, and corner transform
are linked through `trimmed_image_sources`.

**Check is a metadata operation, not a crop operation.** It reads the original
holder photo through `_banknote_vision_source` to identify the note and its PMG /
PCGS label, but does not change either displayed image, the image files, or the
saved corner transforms. Applying Check's suggestions also leaves them alone.
Catalog dimensions are still suggested, including the existing dimension lookup
fallback, but newly learned dimensions must not trigger image processing.

To change a crop, upload a replacement photo or use the image's **Adjust crop**
control. A manual adjustment also survives subsequent Check runs.

## Regression: Canada 1937 $20, September 20, 2026

The initial PMG-holder uploads produced aligned crops. Check then re-ran corner
detection on both originals using newly discovered catalog dimensions. The front
changed from 1189×571 to 1190×577 pixels and the back from 1190×569 to 1190×533.
At a shared display height this enlarged the back relative to the front. Repeated
Check runs could also silently replace manually corrected crops.

The fix removes re-cropping from Check while retaining upload processing,
original-holder label reading, dimension suggestions, and explicit corner edits.
For this record, the saved pre-Check crops can be reattached without processing
the photos again or changing the catalog / grading data.

Regression coverage: `tests/test_banknote_check_preserves_images.py` exercises
upload, initial and repeated Check, new / revised / missing dimensions, manual
adjustment, older unmapped photos, failed lookups, and applying suggestions.
It checks image pointers, file hashes, and source / corner mappings. Holder-label
source selection remains covered by `tests/test_banknote_vision_source.py`.

## Upload quality and full-paper boundaries

Banknote uploads bypass general display-photo optimization: supported opaque
WebP / JPEG / PNG sources remain unchanged, at their original resolution, for
holder-label reading and future crop edits. This applies to drag/drop, form
uploads, imports and Market Buy/Bought. Other categories retain their existing
optimization policy. The existing compatibility conversion for HEIC / transparent
images is unchanged.

Banknote crop JPEGs retain native crop resolution and use quality 97 with full
4:4:4 colour sampling. A high-confidence paper-boundary detector handles cream
paper in a pale cool-coloured holder before the model/cascade pipeline: all four
sides must show the paper-to-holder colour transition, the outline must form a
large rectangle, and any known catalog aspect ratio must agree. It rectifies
directly from the source once and records the exact corners; no later design
crop, edge shave, or tilt correction runs over this accepted full-sheet crop.
Ambiguous photos continue through the existing detectors.

This fixes the Canada 1935 $5 upload (September 20, 2026), whose reverse had been
cropped to the red engraving rather than the full sheet and whose upload had
already been JPEG-compressed before trimming. Tests in
`tests/test_banknote_image_quality.py` cover full paper margins, colour sampling,
native resolution, exact source preservation, and rejection of an inner coloured
design / already cropped note / uncertain surround.
