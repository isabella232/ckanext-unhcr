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

RIDL uses the following KoBo endpoints:
 - https://kobo.unhcr.org/api/v2/assets.json: To get a list of usres' surveys.
 - https://kobo.unhcr.org/api/v2/assets/{ASSET_ID}.json: To get a survey's data.
 - https://kobo.unhcr.org/api/v2/me: To get a KoBo user's information.
 - https://kobo.unhcr.org/api/v2/permissions/manage_asset.json: To get a KoBo user's permissions.
 - https://kobo.unhcr.org/api/v2//api/v2/users/{KOBO_USER_NAME}.json
 - https://kobo.unhcr.org/api/v2/assets/{ASSET_ID}/data.json: To get a survey's data.
 - https://kobo.unhcr.org/api/v2/assets/{ASSET_ID}/exports/: To get a survey's exports.
 - https://kobo.unhcr.org/api/v2/assets/{ASSET_ID}/exports/{EXPORT_ID}/: To get a survey's export details.
 - https://kobo.unhcr.org/api/v2/assets/{ASSET_ID}.{FORMAT}: To get a survey's questionnaire data in a given format.
 - https://kobo.unhcr.org/api/v2/assets/{ASSET_ID}/exports: **POST** To create a new export.
