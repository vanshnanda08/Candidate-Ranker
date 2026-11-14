"""Confirmed-label persistence without opening ranking manifests."""
import csv
import io
import os
from pathlib import Path
import tempfile

GRADES = ('0', '1', '2', '3', 'U')
LABEL_FIELDS = ('relevance_grade', 'reason')


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or not {'review_id', *LABEL_FIELDS} <= set(fields):
            raise ValueError('Invalid or duplicate CSV columns')
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed CSV row width')
    return fields, rows


def _by_id(rows):
    result = {}
    for row in rows:
        rid = row.get('review_id')
        if not isinstance(rid, str) or not rid.strip() or rid in result:
            raise ValueError('Missing or duplicate review_id')
        result[rid] = row
    return result


def validate_labels(original, labeled, *, require_complete=False, expected_count=None):
    source, labels = _by_id(original), _by_id(labeled)
    if expected_count is not None and len(source) != expected_count:
        raise ValueError(f'Expected {expected_count} review rows')
    if set(source) != set(labels):
        raise ValueError('Labeled review IDs do not exactly match the original pool')
    for rid, row in labels.items():
        if set(row) != set(source[rid]):
            raise ValueError(f'Changed columns for {rid}')
        if any(row[field] != source[rid][field] for field in row if field not in LABEL_FIELDS):
            raise ValueError(f'Changed evidence for {rid}')
        grade, reason = row['relevance_grade'], row['reason']
        if not isinstance(grade, str) or grade not in ('', *GRADES):
            raise ValueError(f'Invalid relevance_grade for {rid}')
        if not isinstance(reason, str) or (grade and not reason.strip()) or (not grade and reason.strip()):
            raise ValueError(f'Grade/reason must be confirmed together for {rid}')
    incomplete = sum(not row['relevance_grade'] for row in labels.values())
    if require_complete and incomplete:
        raise ValueError(f'Review incomplete: {incomplete} profiles still need a confirmed grade and reason')
    return labels


def load_progress(original_path, labeled_path):
    fields, original = read_csv(original_path)
    if Path(labeled_path).exists():
        saved_fields, saved = read_csv(labeled_path)
        if saved_fields != fields:
            raise ValueError('Labeled CSV columns differ from the original')
        labels = validate_labels(original, saved)
        return fields, original, [labels[row['review_id']] for row in original]
    # Only explicit confirmations may populate a new labeled file.
    return fields, original, [dict(row, relevance_grade='', reason='') for row in original]


def next_batch(original_path, labeled_path, size=5):
    _, _, rows = load_progress(original_path, labeled_path)
    return [row for row in rows if not row['relevance_grade']][:size]


def save_confirmed(original_path, labeled_path, confirmations):
    """Apply only explicit confirmations; never silently revise a confirmed label."""
    original_path, labeled_path = Path(original_path), Path(labeled_path)
    if original_path.resolve() == labeled_path.resolve():
        raise ValueError('The labeled file must be separate from the original')
    if not confirmations:
        raise ValueError('No confirmed labels supplied; nothing saved')
    fields, original, rows = load_progress(original_path, labeled_path)
    labels = _by_id(rows)
    updates = _by_id(confirmations)
    for rid, update in updates.items():
        if set(update) != {'review_id', *LABEL_FIELDS} or rid not in labels:
            raise ValueError('Unknown review ID or unexpected confirmation fields')
        grade, reason = update['relevance_grade'], update['reason']
        if grade not in GRADES or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f'A valid confirmed grade and reason are required for {rid}')
        old = labels[rid]
        if old['relevance_grade'] and any(old[field] != update[field] for field in LABEL_FIELDS):
            raise ValueError(f'{rid} is already confirmed; explicit revision is required')
        old.update({field: update[field] for field in LABEL_FIELDS})
    validate_labels(original, rows)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=labeled_path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(stream.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, labeled_path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return sum(bool(row['relevance_grade']) for row in rows)
