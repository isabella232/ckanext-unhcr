"""
Run AWS insight query for ridl-prod lñog group (last 6 months)

fields @timestamp, @message
| filter @message like "&rows=21&q="
| sort @timestamp desc

"""
import csv
import re


origin_file = open('scripts/data/logs-insights-results.csv')
reader = csv.DictReader(origin_file)

results_file = open('scripts/data/logs-insights-final.csv', 'w')
fieldnames = ['timestamp', 'query search']
writer = csv.DictWriter(results_file, fieldnames=fieldnames)
writer.writeheader()

for row in reader:
    ts = row['@timestamp']
    msg = row['@message'].strip()
    query = re.search(r'&rows=\d+&q=([^&]*)&', msg)
    query_search = query.group(1) if query else 'NO QUERY'

    writer.writerow({
        'timestamp': row['@timestamp'],
        'query search': query_search
    })
