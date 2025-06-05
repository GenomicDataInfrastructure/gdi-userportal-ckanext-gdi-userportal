# SPDX-FileCopyrightText: 2024 PNED G.I.E.
#
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError, BotoCoreError
from ckan.plugins.toolkit import config
from ckanext.dcat.processors import RDFParserException

from ckanext.gdi_userportal.harvesters import S3RDFHarvester


@pytest.fixture
def mock_harvest_source():
    class MockSource:
        id = "test-harvest-source-id"
        url = "s3://my-endpoint/my-bucket"
        config = None
        owner_org = None
    return MockSource()

@pytest.fixture
def mock_harvest_job(mock_harvest_source):

    class MockJob:
        id = "test-harvest-job-id"
        source_id = mock_harvest_source.id
        source = mock_harvest_source
    return MockJob()

@pytest.fixture
def s3_rdf_harvester():
    return S3RDFHarvester()


@pytest.fixture(autouse=True)
def mock_harvest_gather_error_create():
    with patch("ckanext.harvest.model.HarvestGatherError.create") as mock_create:
        yield mock_create
        
@pytest.fixture(autouse=True)
def mock_save_gather_error():
    with patch.object(S3RDFHarvester, "_save_gather_error") as mock_save:
        yield mock_save


@pytest.fixture
def mock_harvestobject_patch():

    with patch("ckanext.gdi_userportal.harvesters.s3_rdf_harvester.HarvestObject") as ho_cls:
        created_object_ids = []
        def side_effect_constructor(**kwargs):
            new_id = f"harvest-obj-{len(created_object_ids)+1}"
            ho_mock = MagicMock()
            ho_mock.id = new_id
            ho_mock.save = MagicMock()
            ho_mock.content = kwargs.get('content', None)
            created_object_ids.append(new_id)
            return ho_mock

        ho_cls.side_effect = side_effect_constructor

        def side_effect_get(obj_id):
            get_mock = MagicMock()
            get_mock.id = obj_id
            get_mock.content = '{"title": "Dummy fetched content"}'
            return get_mock
        ho_cls.get.side_effect = side_effect_get

        yield created_object_ids

@pytest.fixture
def mock_harvestsource_patch():
    with patch("ckanext.harvest.model.HarvestSource.get") as hs_get:
        mock_source_package = MagicMock()
        mock_source_package.owner_org = "org-id"
        hs_get.return_value = mock_source_package
        yield

@pytest.fixture
def mock_mark_deletion_patch():
    with patch.object(S3RDFHarvester, "_mark_datasets_for_deletion", return_value=[]):
        yield

@pytest.fixture
def mock_save_gather_error_patch():
    with patch.object(S3RDFHarvester, "_save_gather_error") as mock_save:
        yield mock_save


class TestS3RDFHarvesterGatherStage:

    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    def test_gather_stage_no_objects_found(
            self, mock_get_s3_client_info,
            s3_rdf_harvester, mock_harvest_job
    ):
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {}  # No 'Contents'
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)

        assert object_ids == [], "Should return an empty list if the bucket has no RDF objects."
        mock_s3.list_objects_v2.assert_called_once_with(Bucket="my-bucket")


    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch.object(S3RDFHarvester, "_save_gather_error")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    @patch('ckanext.gdi_userportal.harvesters.s3_rdf_harvester.RDFParser')
    @patch('ckanext.harvest.model.Package.get')
    def test_gather_stage_success_single_rdf(
            self,
            mock_package_get,
            mock_rdf_parser_cls,
            mock_get_s3_client_info,
            mock_save_gather_error,
            s3_rdf_harvester,
            mock_harvest_job
    ):
        mock_s3 = MagicMock()

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "dataset.rdf"}
            ]
        }

        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: b"<rdf>Some RDF content</rdf>")
        }
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        mock_rdf_parser = MagicMock()

        mock_rdf_parser.datasets.return_value = [{
            "title": "Test Dataset",
            "identifier": "test-guid-1234",
            "extras": []
        }]
        mock_rdf_parser_cls.return_value = mock_rdf_parser


        mock_source_package = MagicMock()
        mock_source_package.owner_org = "org-id"
        mock_source_package.url = "http://dataset/testurl"
        mock_package_get.return_value = mock_source_package

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)

        assert not mock_save_gather_error.called, \
            f"An error was logged instead of creating a HarvestObject: {mock_save_gather_error.call_args_list}"

        assert len(object_ids) == 1, "Should produce exactly one HarvestObject ID."

    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    @patch('ckanext.dcat.processors.RDFParser')
    def test_gather_stage_rdf_parser_exception(
            self,
            mock_rdf_parser_cls,
            mock_get_s3_client_info,
            s3_rdf_harvester,
            mock_harvest_job
    ):

        mock_s3 = MagicMock()

        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "bad_dataset.rdf"}
            ]
        }
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: b"bad RDF content")
        }
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        mock_rdf_parser = MagicMock()
        mock_rdf_parser.parse.side_effect = RDFParserException("Parse error")
        mock_rdf_parser_cls.return_value = mock_rdf_parser

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)

        assert object_ids == [], "Should return empty list when parse fails."


    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    def test_gather_stage_aws_client_error(
            self, mock_get_s3_client_info,
            s3_rdf_harvester, mock_harvest_job
    ):
        mock_s3 = MagicMock()
        error_response = {
            'Error': {
                'Code': 'AccessDenied',
                'Message': 'Access Denied'
            }
        }
        mock_s3.list_objects_v2.side_effect = ClientError(error_response, "ListObjects")
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)
        assert object_ids == []


    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    def test_gather_stage_boto_core_error(
            self, mock_get_s3_client_info,
            s3_rdf_harvester, mock_harvest_job
    ):
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = BotoCoreError(error_msg="Some BotoCore error")
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)
        assert object_ids == []


    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    def test_gather_stage_unexpected_error(
            self, mock_get_s3_client_info,
            s3_rdf_harvester, mock_harvest_job
    ):
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = RuntimeError("Unknown error")
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)
        assert object_ids == []


    @pytest.mark.usefixtures("mock_harvestobject_patch",
                             "mock_harvestsource_patch",
                             "mock_mark_deletion_patch",
                             "mock_save_gather_error_patch")
    @patch('ckanext.harvest.model.Package.get')
    @patch.object(S3RDFHarvester, "_save_gather_error")
    @patch.object(S3RDFHarvester, '_get_s3_client_info')
    @patch('ckanext.gdi_userportal.harvesters.s3_rdf_harvester.RDFParser')
    def test_gather_stage_with_custom_rdf_format(
            self,
            mock_rdf_parser_cls,
            mock_get_s3_client_info,
            mock_save_gather_error,
            mock_package_get,
            s3_rdf_harvester,
            mock_harvest_job
    ):
        mock_harvest_job.source.config = json.dumps({"rdf_format": "turtle"})

        mock_source_package = MagicMock()
        mock_source_package.owner_org = "org-id"
        mock_package_get.return_value = mock_source_package

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "dataset.ttl"}
            ]
        }
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: b"@prefix dcat: <http://www.w3.org/ns/dcat#> .")
        }
        mock_get_s3_client_info.return_value = ("my-bucket", mock_s3)

        mock_rdf_parser = MagicMock()
        mock_rdf_parser.datasets.return_value = [{
            "title": "Test Dataset TTL",
            "identifier": "test-guid-ttl",
            "extras": []
        }]
        mock_rdf_parser_cls.return_value = mock_rdf_parser

        object_ids = s3_rdf_harvester.gather_stage(mock_harvest_job)

        assert not mock_save_gather_error.called, \
            f"An error was logged instead of creating a HarvestObject: {mock_save_gather_error.call_args_list}"

        assert len(object_ids) == 1, "Should create a HarvestObject when custom format is used."
        mock_rdf_parser.parse.assert_called_once_with(
            "@prefix dcat: <http://www.w3.org/ns/dcat#> .",
            _format="turtle"
        )


class TestS3RDFHarvesterGetS3ClientInfo:

    @patch('ckanext.harvest.model.HarvestSource.get')
    def test_get_s3_client_info(
            self, mock_harvestsource_get, s3_rdf_harvester, mock_harvest_job
    ):
        mock_source = MagicMock()
        mock_source.url = "https://my-s3-endpoint.com/my-bucket"
        mock_harvestsource_get.return_value = mock_source

        with patch.object(config, 'get', side_effect=lambda key: {
            'ckan.harvest.s3_rdf.aws_access_key': 'fake_access_key',
            'ckan.harvest.s3_rdf.aws_secret_key': 'fake_secret_key'
        }.get(key)):

            bucket_name, s3_client = s3_rdf_harvester._get_s3_client_info(mock_harvest_job)

        assert bucket_name == "my-bucket"
        assert s3_client is not None
        assert hasattr(s3_client, 'list_objects_v2')
