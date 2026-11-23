"""Bounded A/B: cheaper models for banknote photo work and the Perplexity watch setting.

Compares the current settings with cheaper candidates on SAMPLE inputs only
(never the production database): photos you pass with --photos (copied into a
temporary data folder) and a few watch references passed with --watch. A hard
cap stops the run at --max-calls paid requests (default 40).

    ANTHROPIC_API_KEY=... PERPLEXITY_API_KEY=... python3 scripts/ab-cheaper-models.py \
        --photos ~/Desktop/sample-notes --watch "F.P. Journe|Chronometre Bleu|CB" \
        --watch "Omega|Speedmaster Professional|311.30.42.30.01.005"

Areas and what "match" means:
  trim geometry  (ANTHROPIC_TRIM_MODEL)        holder/label flags equal and every corner
                                                within 20/1000 of the frame
  photo sides    (ANTHROPIC_PHOTO_SIDES_MODEL) same front/back picks and the same side
                                                and confidence for every photo
  watch lookup   (PERPLEXITY_WATCH_LOOKUP_SEARCH_CONTEXT) every non-null spec field
                                                equal (case-insensitive)

Switch a setting only where every compared item matches; set it on BOTH Railway
services (web and gerri). Prints a JSON report.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--photos', help='folder of sample banknote photos (jpg/png/webp)')
    parser.add_argument('--watch', action='append', default=[], help='"Brand|Model|Reference" (repeatable)')
    parser.add_argument('--trim-candidate', default='auto-haiku')
    parser.add_argument('--sides-candidate', default='auto-haiku')
    parser.add_argument('--context-candidate', default='medium', choices=('low', 'medium'))
    parser.add_argument('--max-photos', type=int, default=6)
    parser.add_argument('--max-calls', type=int, default=40)
    args = parser.parse_args()
    need_anthropic = bool(args.photos)
    need_perplexity = bool(args.watch)
    missing = [name for name, needed in (('ANTHROPIC_API_KEY', need_anthropic), ('PERPLEXITY_API_KEY', need_perplexity))
               if needed and not os.environ.get(name)]
    if missing or not (need_anthropic or need_perplexity):
        sys.exit('Nothing to compare, or missing ' + ', '.join(missing or ['--photos/--watch']) + '. No calls made.')

    data_dir = tempfile.mkdtemp(prefix='stuff-ab-')
    os.environ.update(DATA_DIR=data_dir, ENRICHMENT_REPLAY_SECONDS='0', EBAY_SYNC_WORKER='0',
                      BANKNOTE_IMPORT_WORKER='0', ORIGINAL_LISTING_WORKER='0', MARKET_LABEL_WORKER='0')
    sys.path.insert(0, str(ROOT))
    import enrichment
    original_record = enrichment.record_call
    budget = {'used': 0}

    def capped(*a, **kw):
        budget['used'] += 1
        original_record(*a, **kw)
        if budget['used'] >= args.max_calls:
            raise SystemExit(f'Hard cap of {args.max_calls} paid calls reached; stopping.')
    enrichment.record_call = capped
    import app as stuff
    from PIL import Image

    report = {'max_calls': args.max_calls}
    if args.photos:
        uploads = Path(stuff.UPLOAD_FOLDER)
        uploads.mkdir(parents=True, exist_ok=True)
        photos = sorted(p for p in Path(args.photos).expanduser().iterdir()
                        if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'))[:args.max_photos]
        for photo in photos:
            shutil.copy(photo, uploads / photo.name)

        def geometry(model):
            os.environ['ANTHROPIC_TRIM_MODEL'] = model
            out = {}
            for photo in photos:
                with Image.open(uploads / photo.name) as image:
                    out[photo.name] = stuff._note_geometry_scan(image.convert('RGB'))
            return out
        current_trim = os.environ.get('ANTHROPIC_TRIM_MODEL') or os.environ.get('ANTHROPIC_NOTE_QUAD_MODEL') or 'auto-sonnet'
        a, b = geometry(current_trim), geometry(args.trim_candidate)

        def same_geometry(x, y):
            if not x or not y:
                return x == y
            corners = max(abs(p[i] - q[i]) for p, q in zip(x['quad'], y['quad']) for i in (0, 1))
            return x['holder'] == y['holder'] and x['label'] == y['label'] and corners <= 20
        report['trim_geometry'] = dict(current=current_trim, candidate=args.trim_candidate,
                                       items={name: same_geometry(a[name], b[name]) for name in a})

        def sides(model):
            os.environ['ANTHROPIC_PHOTO_SIDES_MODEL'] = model
            entries = [dict(id=f'photo-{i}', filename=p.name, gallery=True) for i, p in enumerate(photos)]
            try:
                return stuff._classify_banknote_listing_photos(entries)
            except Exception as error:
                return {'error': type(error).__name__}
        current_sides = os.environ.get('ANTHROPIC_PHOTO_SIDES_MODEL') or os.environ.get('ANTHROPIC_NOTE_QUAD_MODEL') or 'auto-sonnet'
        x, y = sides(current_sides), sides(args.sides_candidate)

        def reading(decision):
            return {p.get('id'): (p.get('side'), p.get('confidence')) for p in decision.get('photos', [])}
        report['photo_sides'] = dict(current=current_sides, candidate=args.sides_candidate,
                                     match=(x.get('front'), x.get('back'), reading(x)) == (y.get('front'), y.get('back'), reading(y)))

    if args.watch:
        def lookup(context, brand, model, reference):
            os.environ['PERPLEXITY_WATCH_LOOKUP_SEARCH_CONTEXT'] = context
            row = {key: None for key in ('calibre', 'case_num', 'movement_num', 'date', 'description', 'notes', 'year')}
            row.update(brand=brand, model=model, reference=reference)
            return stuff.fetch_watch_specs(row)
        items = {}
        for spec in args.watch:
            brand, model, reference = (spec.split('|') + ['', '', ''])[:3]
            high, cheap = lookup('high', brand, model, reference), lookup(args.context_candidate, brand, model, reference)
            fields = [k for k in high if k not in ('sources', 'notes', 'calibre_notes') and high.get(k) is not None]
            items[spec] = all(str(high[k]).lower() == str(cheap.get(k)).lower() for k in fields)
        report['watch_lookup'] = dict(current='high', candidate=args.context_candidate, items=items)

    report['paid_calls'] = budget['used']
    report['usage'] = enrichment.usage_snapshot()
    print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main()
