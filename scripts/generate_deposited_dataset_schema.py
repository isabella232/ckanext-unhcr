import json
from collections import OrderedDict


# Module API

INPUT_JSON = 'ckanext/unhcr/schemas/dataset.json'
OUTPUT_JSON = 'ckanext/unhcr/schemas/deposited_dataset.json'

def generate_deposited_dataset_schema():

    # Read `dataset` schema
    with open(INPUT_JSON) as file:
        schema = OrderedDict(json.load(file))

    # Update dataset type
    schema['dataset_type'] = 'deposited-dataset'
    schema['warning'] = 'This is an automatically generated file. Do not change it manually.'

    # Remove dataset required flags
    for field in schema['dataset_fields']:
        if field['field_name'] not in ['title']:
            field['required'] = False

    # Remove resource required flags
    for field in schema['resource_fields']:
        if field['field_name'] not in ['title', 'type', 'visibility']:
            field['required'] = False

    for field in schema['dataset_fields'] + schema['resource_fields']:
        if field.get('preset') == 'select':
            if field['field_name'] not in ['visibility', 'file_type', 'type']:
                if not field.get('validators'):
                    field['validators'] = 'ignore_empty scheming_required scheming_choices'
                elif (
                    field.get('validators') and
                    not field['validators'].startswith('ignore_empty')
                ):
                    field['validators'] = 'ignore_empty ' + field['validators']

    # Handle organization fields
    for index, field in enumerate(list(schema['dataset_fields'])):
        if field['field_name'] == 'owner_org':

            # owner_org
            field['form_snippet'] = None
            field['display_snippet'] = None
            field['validators'] = 'deposited_dataset_owner_org'
            field['required'] = True

            # owner_org_dest
            schema['dataset_fields'].insert(index + 1, {
                'field_name': 'owner_org_dest',
                'label': 'Data Container',
                'form_snippet': 'owner_org_dest.html',
                'display_snippet': 'owner_org_dest.html',
                'validators': 'deposited_dataset_owner_org_dest',
                'required': True,
            })

            # curation_state
            schema['dataset_fields'].insert(index + 1, {
                'field_name': 'curation_state',
                'form_snippet': 'hidden.html',
                'display_snippet': None,
                'validators': 'deposited_dataset_curation_state',
                'required': True,
            })

            # curation_final_review
            schema['dataset_fields'].insert(index + 1, {
                'field_name': 'curation_final_review',
                'form_snippet': 'hidden.html',
                'display_snippet': None,
            })

            # curator_id
            schema['dataset_fields'].insert(index + 1, {
                'field_name': 'curator_id',
                'form_snippet': 'hidden.html',
                'display_snippet': None,
                'validators': 'ignore_missing deposited_dataset_curator_id',
            })

    # Write `deposited-dataset` schema tweaking order
    with open(OUTPUT_JSON, 'w') as file:
        schema['dataset_fields'] = schema.pop('dataset_fields')
        schema['resource_fields'] = schema.pop('resource_fields')
        json.dump(schema, file, indent=4)

    print('Schema for the `deposited-dataset` type has been generated')


# Main script

if __name__ == '__main__':
    generate_deposited_dataset_schema()
