VALID_KOBO_EXPORT_FORMATS = {
    "csv": "CSV",
    "xls": "XLS",
    "spss_labels": "SPSS Labels (ZIP)",
    "geojson": "GeoJSON (only useful if geographic data exists)"
}

CUSTOM_KOBO_EXPORT_FORMATS = {
    "json": "JSON (custom download with all data, no filters will be applied)"
}

ALL_KOBO_EXPORT_FORMATS = {
    **VALID_KOBO_EXPORT_FORMATS,
    **CUSTOM_KOBO_EXPORT_FORMATS
}

FIXED_FIELDS_KOBO_EXPORT = [
    "_id", "_uuid", "_submission_time", "_validation_status", "_notes",
    "_status", "_submitted_by", "_tags", "_index"
]
