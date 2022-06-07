# KoBo on RIDL

## About KoBo

[KoBoToolbox](https://www.kobotoolbox.org/#home)
is a [free & open source](https://github.com/kobotoolbox)
suite of tools for field data collection for use in challenging environments.  

## RIDL with KoBoToolbox

Before the current KoBo integration, users had to download data from KoBo and re-upload it to RIDL manually.
UNHCR has its own KoBo instance at [kobo.unhcr.org](https://kobo.unhcr.org) (if this
change in the future you'll need to update the `ckanext.unhcr.kobo_url` RIDL setting).  

RIDL currently allows KoBo users to:
 - Set up a KoBo token for each RIDL user.
 - List all your KoBo surveys.
 - Import KoBo surveys as RIDL datasets.
 - Sync imported KoBo surveys with new or updated submissions.

### Data Integration

RIDL uses the KoBo API ([docs here](https://support.kobotoolbox.org/api.html))
to obtain all the necessary data.  

Internally, we handle this connection with these two files:
 - [api.py](https://github.com/okfn/ckanext-unhcr/blob/master/ckanext/unhcr/kobo/api.py): 
To interact with the KoBo API.
 - [kobo_dataset.py](https://github.com/okfn/ckanext-unhcr/blob/master/ckanext/unhcr/kobo/kobo_dataset.py): 
To transform KoBo data to RIDL datasets.

### KoBo endpoints in use

RIDL uses the following KoBo endpoints (at https://kobo.unhcr.org):
 - /api/v2/assets.json: To get a list of usres' surveys.
 - /api/v2/assets/{ASSET_ID}.json: To get a survey's data.
 - /me: To get a KoBo user's information.
 - /api/v2/permissions/manage_asset.json: To get a KoBo user's permissions.
 - /api/v2/users/{KOBO_USER_NAME}.json
 - /api/v2/assets/{ASSET_ID}/data.json: To get a survey's data.
 - /api/v2/assets/{ASSET_ID}/exports/: **POST** To create a new survey export.
 - /api/v2/assets/{ASSET_ID}/exports/{EXPORT_ID}/: To get a survey's export details.
 - /api/v2/assets/{ASSET_ID}.{FORMAT}: To get a survey's questionnaire data in a given format.
 - /api/v2/assets/{ASSET_ID}/exports: **POST** To create a new export.

#### Create a new export

To generate a new export you should POST to `/api/v2/assets/{ASSET_ID}/exports/` with the following data:
 - `"fields_from_all_versions"` (required) is a boolean to specify whether fields from all form versions will be included in the export.
 - `"group_sep"` (required) is a value used to separate the names in a hierarchy of groups. Valid inputs include:
Non-empty value
 - `"hierarchy_in_labels"` (required) is a boolean to specify whether the group hierarchy will be displayed in labels
 - `"multiple_select"` (required) is a value to specify the display of multiple_select-type responses. Valid inputs include:
   - `"both"`,
   - `"summary"`, or
   - `"details"`
 - `"type"` (required) specifies the export format. Valid export formats include:
   - `"csv"`,
   - `"geojson"`,
   - `"spss_labels"`, or
   - `"xls"`
   - `"fields"` (optional) is an array of column names to be included in the export (including their group hierarchy). Valid inputs include:
An array containing any string value that matches the XML column name
An empty array which will result in all columns being included
If "fields" is not included in the "export_settings", all columns will be included in the export
 - `"flatten"` (optional) is a boolean value and only relevant when exporting to "geojson" format.
 - `"xls_types_as_text"` (optional) is a boolean value that defaults to "false" and only affects "xls" export types.
 - `"include_media_url"` (optional) is a boolean value that defaults to "false" and only affects "xls" and "csv" export types. This will include an additional column for media-type questions ("question_name_URL") with the URL link to the hosted file.
"submission_ids" (optional) is an array of submission ids that will filter exported submissions to only the specified array of ids. Valid inputs include:
An array containing integer values
An empty array (no filtering)
 - `"query"` (optional) is a JSON object containing a Mongo filter query for filtering exported submissions. Valid inputs include:
A JSON object containing a valid Mongo query
An empty JSON object (no filtering)

Payload sample:

```json
   {
      "fields_from_all_versions": "true",
      "group_sep": "/",
      "hierarchy_in_labels": "true",
      "lang": "English (en)",
      "multiple_select": "both",
      "type": "geojson",
      "fields": ["field_1", "field_2"],
      "flatten": "true"
      "xls_types_as_text": "false",
      "include_media_url": "false",
      "submission_ids": [1, 2, 3, 4],
      "query": {
         "$and": [
             {"_submission_time": {"$gte": "2021-08-31"}},
             {"_submission_time": {"$lte": "2021-10-13"}}
         ]
       }
     }
   }
```
