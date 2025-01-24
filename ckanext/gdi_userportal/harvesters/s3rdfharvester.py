# SPDX-FileCopyrightText: 2023 Civity
# SPDX-FileContributor: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: AGPL-3.0-only

import boto3
import json
import logging
from urllib.parse import urlparse

import ckan.model as model
from ckanext.harvest.model import HarvestObject, HarvestSource
from ckan.plugins.toolkit import config
from ckanext.dcat.processors import RDFParserException, RDFParser
from ckanext.dcat.harvesters.rdf import DCATRDFHarvester

log = logging.getLogger(__name__)

class S3RDFHarvester(DCATRDFHarvester):

    def info(self):
        return {
            'name': 's3_rdf',
            'title': 'S3 RDF Harvester',
            'description': 'Harvests RDF files from an S3 bucket.'
        }

    def gather_stage(self, harvest_job):
        log.info('In S3RDFHarvester gather_stage')

        bucket_name, s3 = self._get_s3_client_info(harvest_job)
        rdf_format = None
        if harvest_job.source.config:
            rdf_format = json.loads(harvest_job.source.config).get("rdf_format")

        try:
            # List objects in the S3 bucket
            s3_objects = s3.list_objects_v2(Bucket=bucket_name)
            if 'Contents' not in s3_objects:
                self._save_gather_error('No objects found in the S3 bucket', harvest_job)
                return []
            guids_in_source = []
            object_ids = []
            self._names_taken = []

            for obj in s3_objects['Contents']:
                key = obj['Key']
                if not (key.endswith('.rdf') | key.endswith('.ttl')):
                    continue
                # Download the object from S3
                s3_object = s3.get_object(Bucket=bucket_name, Key=key)
                content = s3_object['Body'].read().decode('utf-8')
                parser = RDFParser()
                try:
                    parser.parse(content, _format=rdf_format)
                except RDFParserException as e:
                    self._save_gather_error(f'Error parsing the RDF file {key}: {e}', harvest_job)
                    continue

                source_dataset = model.Package.get(harvest_job.source.id)

                for dataset in parser.datasets():
                    if not dataset.get('name'):
                        dataset['name'] = self._gen_new_name(dataset['title'])
                    if dataset['name'] in self._names_taken:
                        suffix = len([i for i in self._names_taken if i.startswith(dataset['name'] + '-')]) + 1
                        dataset['name'] = f"{dataset['name']}-{suffix}"
                    self._names_taken.append(dataset['name'])

                    if not dataset.get('owner_org') and source_dataset.owner_org:
                        dataset['owner_org'] = source_dataset.owner_org

                    guid = self._get_guid(dataset, source_url=source_dataset.url)

                    if not guid:
                        self._save_gather_error(f'Could not get a unique identifier for dataset: {dataset}', harvest_job)
                        continue

                    dataset['extras'].append({'key': 'guid', 'value': guid})
                    guids_in_source.append(guid)

                    obj = HarvestObject(guid=guid, job=harvest_job,
                                        content=json.dumps(dataset))

                    obj.save()
                    object_ids.append(obj.id)

            object_ids_to_delete = self._mark_datasets_for_deletion(guids_in_source, harvest_job)
            object_ids.extend(object_ids_to_delete)

            return object_ids

        except Exception as e:
            self._save_gather_error(f'Error accessing S3 bucket: {e}', harvest_job)
            return []

    def _get_s3_client_info(self, harvest_job):
        # Load S3 configuration
        aws_access_key = config.get('ckan.harvest.s3_rdf.aws_access_key')
        aws_secret_key = config.get('ckan.harvest.s3_rdf.aws_secret_key')
        harvest_source = HarvestSource.get(harvest_job.source_id, attr="id")
        parsed_url = urlparse(harvest_source.url)
        endpoint = f"{parsed_url.scheme}://{parsed_url.netloc}"  # Scheme + Host
        path_parts = parsed_url.path.strip("/").split("/")  # Split the path
        bucket_name = path_parts[0] if path_parts else None  # First part of the path
        # Initialize S3 client with authentication
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        return bucket_name, s3

    def fetch_stage(self, harvest_object):
        return super(S3RDFHarvester, self).fetch_stage(harvest_object)

    def import_stage(self, harvest_object):
        return super(S3RDFHarvester, self).import_stage(harvest_object)

    def _create_or_update_package(self, dataset_dict, harvest_object):
        return super(S3RDFHarvester, self)._create_or_update_package(dataset_dict, harvest_object)

    def _create_package(self, dataset_dict):
        return super(S3RDFHarvester, self)._create_package(dataset_dict)

    def _update_package(self, dataset_dict):
        return super(S3RDFHarvester, self)._update_package(dataset_dict)

    def _save_package(self, dataset_dict, action):
        return super(S3RDFHarvester, self)._save_package(dataset_dict, action)