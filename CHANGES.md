# RIDL Changelog

## v3.1.3 - 2021-09-08
New features
 - [#687](https://github.com/okfn/ckanext-unhcr/pull/687) Improve information about requests for new/renewal external user
 - [#681](https://github.com/okfn/ckanext-unhcr/pull/681) Show new submissions to update KoBo datasets
 - [#672](https://github.com/okfn/ckanext-unhcr/pull/672) Allow skipping ClamAV for fake KoBo resources
 - [#683](https://github.com/okfn/ckanext-unhcr/pull/683) Allow sorting and searching at KoBo survey list

## v3.1.2b - 2021-08-25 

New features
- [KoBo tutorial](https://github.com/okfn/ckanext-unhcr/blob/c34c4a50e4122a3e26558913d651369bc65b6e82/docs/kobo.md) created
- [#666](https://github.com/okfn/ckanext-unhcr/pull/666) Prevent uploading files to automatically imported KoBo resources
- [#671](https://github.com/okfn/ckanext-unhcr/pull/671) Use Kobo survey submission count to validate

## v3.1.2 - 2021-08-10

New features
- [#628](https://github.com/okfn/ckanext-unhcr/pull/628) Move visibility as resource field
- [#604](https://github.com/okfn/ckanext-unhcr/pull/604) Expire external users after 180 days and handle renewal requests
- [#637](https://github.com/okfn/ckanext-unhcr/pull/637) + [#657](https://github.com/okfn/ckanext-unhcr/pull/657) + [#662](https://github.com/okfn/ckanext-unhcr/pull/662) Allow users to integrate with KoBo and import surveys as datasets + resources. This includes the questionnaire and the actual data in JSON/CSV and XLS formats.
Bug fixes:
- [#642](https://github.com/okfn/ckanext-unhcr/pull/642) Improve styles for curation activities
- [#661](https://github.com/okfn/ckanext-unhcr/pull/661) Show pending requests for data containers

## v3.1.1b - 2021-08-03

Bug fixes:
- Help texts 
  - [#646](https://github.com/okfn/ckanext-unhcr/issues/646) / [#639](https://github.com/okfn/ckanext-unhcr/pull/639)
  - [#647](https://github.com/okfn/ckanext-unhcr/issues/647) / [#653](https://github.com/okfn/ckanext-unhcr/pull/653)
  - [#648](https://github.com/okfn/ckanext-unhcr/issues/648) / [#654](https://github.com/okfn/ckanext-unhcr/pull/654)
- Warning for access pending to approve [#649](https://github.com/okfn/ckanext-unhcr/issues/649) / [#655](https://github.com/okfn/ckanext-unhcr/pull/655)
- Fix email footer [#650](https://github.com/okfn/ckanext-unhcr/issues/650) / [#656](https://github.com/okfn/ckanext-unhcr/pull/656)

## v3.1.1 - 2021-07-14

Bug fixes:
- Fix users login [#632](https://github.com/okfn/ckanext-unhcr/pull/632/files?diff=split&w=1)

## v3.1.0 - 2021-07-14

Features:
- Python 3 support. RIDL no longer supports Python 2. There are no related user facing changes.

Bug fixes:
- Fix exception when Requesting Data Containers. When requesting a new data container to be nested
  inside another one, you now have to be an admin of the parent data container.


## v3.0.1 - 2021-06-22

Bug fixes:
- Fix pagination on data container pages
- Hide activities from site user
- Adopt package_revise in background jobs to resolve some race conditions for API users
- Fix resource icon sizes

## v3.0.0 - 2021-06-14

Behaviour changes:
- SAML2 SSO: Logging out of RIDL no longer logs out of Active Directory
- API keys are no longer auto-generated for new users. CKAN 2.9 introduces a new feature: API Tokens
  see https://docs.ckan.org/en/2.9/api/index.html#api-authentication

Bug fixes:
- Fixed 500 error when requesting password reset for nonexistant user or searching user list with zero results
- Fixed copying dataset with tags
- Fixed request access dialog on resource pages
- Active menu tab is always marked active on dataset pages
- Fixed missing 'manage' link on container read page
- Fixed missing fields on About page for containers

Features:
- A full history of dataset changes is now displayed in the Activity Stream to admins
- CKAN 2.9 supports python3, enabling us to work on the python3 migration next

## v2.3.3 - 2021-06-11

- Minor formatting change in MFA banner

## v2.3.2 - 2021-06-11

- Show MFA banner

## v2.3.1 - 2021-05-11

Fixes:
- Fix error copying datasets with tags

## v2.3.0 - 2021-05-06

Features:
- Include google analytics tracking code

## v2.2.1 - 2021-03-25

Fixes:
- Improve display of 'external access level' field

## v2.2.0 - 2021-03-16

Features:
- Switch from ckanext-cloudstorage to ckanext-s3filestore

## v2.1.5 - 2021-02-25

Fixes:
- Wrap long dataset titles instead of truncating them

## v2.1.4 - 2021-02-10

Fixes:
- Update schemas for scheming 2
- Don't allow multple users with the same email address

## v2.1.3 - 2021-02-03

Fixes:
- Fix approving external user account requests for contianer admins

## v2.1.2 - 2021-02-02

Fixes:
- Fix access request dashboard display for contianer admins

## v2.1.1 - 2021-02-01

Fixes:
- Improve load times on:
  - External User Signup page,
  - Data Deposit page and
  - Manage Container Membership page

## v2.1.0 - 2021-01-21

Fixes:
- Exclude site user from metrics tables
- Don't allow a draft dataset with zero resources to be published
- Fix 404 and search index corruption when organization slug is changed
- Remove confusing text from membership delete email
- Fix large file uploads via the API
- Resolve failures sending emails when granting access requests to some containers/datasets

## v2.0.2 - 2021-01-20

Fixes:
* Grant external users permissions required for datapusher/resource previews

## v2.0.1 - 2021-01-20

Fixes:
* Grant external users permissions required to submit jobs to Clam AV

## v2.0.0 - 2021-01-20

Features:
* Allow external users to deposit datasets
  See https://github.com/okfn/ckanext-unhcr/milestone/3?closed=1 for more detail

## v1.8.2 - 2020-11-18

Fixes:
* Fix error re-generating API keys
* Show complete list in "related datasets" menu
* Fix pagination links in parent containers

## v1.8.1 - 2020-09-04

Fixes:
* Style 'Data-container' as 'Data Container'
* Always hide 'request access' button from sysadmins
* Fix 'withdraw' popup in curation interface

## v1.8.0 - 2020-07-31

Features:
* Allow management of sysadmins from the web UI
* Improve helper text for dataset title
* Always link to user guide in the sidebar
* Allow users to request access to a data container
* Allow search index to be rebuilt from the web UI

Fixes:
* Allow sort by Created on organization page
* Fix unnecessary scroll bar in MS Edge

## v1.7.0 - 2020-07-15

Features:
* Allow admins to approve/reject dataset access requests from dashboard
* Expose "download resource" activities to container admins
* Silence notifications when uploading a resource
* Explain draft datasets in the sidebar
* Link to the user guide on the landing page
* Show max upload size hint when adding resource

## v1.6.0 - 2020-07-08

Features:
* Show container counts on Manage Membership page
* Allow attachment resources to be a URL
* Updates to helper text when creating datasets
* Add more File Types for attachments
* Allow search results to be ordered by creation date
* Add a banner to visually distinguish UAT from production

Fixes:
* Improve menu styling on mid-resolution screens

## v1.5.0 - 2020-06-23

Features:
* Add 'keywords' table to metrics dashboard
* Show regions/containers in digest emails
* Allow summary emails to be disabled in UAT only
* Include requesting user in "new container" request email

Fixes:
* Fix failure when editing metadata of existing resources

## v1.4.2 - 2020-06-11

Fixes:
* Collaborators can not be added to a deposited dataset

## v1.4.1 - 2020-06-10

Fixes:
* Fix race condition when saving resource using cloudstorage engine
* Improve notification display when using cloudstorage plugin
* Fix labels on "add member" form
* Fix datastore api authentication failure from datapusher job

## v1.4.0 - 2020-05-27

Features:
* Log downloads when using Cloud Storage backend

Fixes:
* Fix user names in "request access" emails

Changes:
* Log downloads with dataset_id, not resource_id

## v1.3.0 - 2020-05-13

Features:
* Enable dataset-level permissions
* Allow users to request access to a dataset
* Show data deposits on metrics page

Fixes:
* Fix auth check on metrics page

## v1.2.0 - 2020-04-30

Features:
* Log resource downloads
* Show dataset downloads on metrics dashboard

Fixes:
* Exclude data deposits from users table on metrics dashboard
* Supress summary emails if there are no events to report

## v1.1.0 - 2020-04-14

* Add metrics dashboard with stats on how the site is used for curation team and sysadmins
* Store number of datasets and containers over time
* Add weekly sumary emails to curation team and sysadmins summarising activity for the past week

## v1.0.7 - 2020-02-11

* Only show resources with erros on curation sidebar

## v1.0.6 - 2020-02-11

* Improve validation errors display in curation interface

## v1.0.5 - 2020-02-11

* Fix exception when a schema field can not be found

## v1.0.4 - 2020-01-13

* Fix bug in resource form that led to malformed download URLs
* Show RIDL version in footer

## v1.0.3 - 2019-12-19

* Fix bug with the DDI import UI
* Fix bug with datasets without a data container
* Fix bug with visual representation of tags

## v1.0.2 - 2019-12-04

* Fix bug preventing editors to copy datasets

## v1.0.1 - 2019-11-18

* Fix modal dialogs in data deposit pages

## v1.0.0 - 2019-11-15

* Upgrade to CKAN 2.8, which contains several performance and design
  improvements
* Switch authentication provider to Azure Active Directory via SAML2,
  which integrates better with the rest of UNHCR infrastructure and
  fixes the following authentication related issues:
    * Users got logged out too frequently
    * Users did not get redirected to the original URL after logging in

## v0.2.0 - 2019-10-31

* New External Access field values, that replace the old licenses
* Remove confusing format helper on date fields
* Always include sub-data containers in dataset searches by default

## v0.1.0 - 2019-08-31

* The "Data Collector" field has been updated to be a free text field
* Updated the data deposition email to be sent after the dataset's publication
* Added an ability to publish a draft dataset with only one resource
* Added additional information for curators on access errors
* Added resource type "Other" to use for DDI files
* Fixed datasets and data containers creation
* Fixed search functionality and dataset counters
* Several minor bug fixes and enhancements

## v0.0.2 - 2019-07-31

* Allow all users to search and browse private datasets (not download them).
* Ability for sysadmins to push datasets to the Microdata library.
* Fixed Dashboard button link for Data Containers.
* Improve fields handling in DDI import.
* Redirect to login page on datasets and data containers if not logged in.
* Email notifications when users get added to a data container.
* Several minor bug fixes and enhancements

## v0.0.1 - 2019-05-30

* Data Deposit feature to provide dataset that don't (yet) conform to the RIDL
  metadata standard. It allows a team of curators to improve or expand the
  provided dataset until it is ready for publication.
* Ability to copy metadata from an existing dataset or resource.
* Administrator pages for managing users membership on Data Containers
* Pending requests page in dashboard for Administrators.
* Several bug fixes and enhancements
