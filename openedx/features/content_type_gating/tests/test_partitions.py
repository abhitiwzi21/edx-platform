from datetime import datetime
from mock import Mock, patch
from django.conf import settings
from django.test import RequestFactory

from courseware.masquerade import CourseMasquerade
from course_modes.tests.factories import CourseModeFactory
from lms.djangoapps.courseware.tests.factories import GlobalStaffFactory
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangolib.testing.utils import CacheIsolationTestCase
from openedx.features.content_type_gating.helpers import CONTENT_GATING_PARTITION_ID
from openedx.features.content_type_gating.partitions import (
    create_content_gating_partition,
    ContentTypeGatingPartition
)
from openedx.features.content_type_gating.models import ContentTypeGatingConfig
from xmodule.partitions.partitions import UserPartitionError, ENROLLMENT_TRACK_PARTITION_ID


class TestContentTypeGatingPartition(CacheIsolationTestCase):
    def setUp(self):
        self.course_key = CourseKey.from_string('course-v1:test+course+key')

    def test_create_content_gating_partition_happy_path(self):

        mock_course = Mock(id=self.course_key, user_partitions={})
        ContentTypeGatingConfig.objects.create(enabled=True, enabled_as_of=datetime(2018, 1, 1))

        with patch('openedx.features.content_type_gating.partitions.ContentTypeGatingPartitionScheme.create_user_partition') as mock_create:
            partition = create_content_gating_partition(mock_course)
            self.assertEqual(partition, mock_create.return_value)

    def test_create_content_gating_partition_override_only(self):
        mock_course = Mock(id=self.course_key, user_partitions={})
        ContentTypeGatingConfig.objects.create(enabled=False, studio_override_enabled=True)

        partition = create_content_gating_partition(mock_course)
        self.assertIsNotNone(partition)

    def test_create_content_gating_partition_disabled(self):
        mock_course = Mock(id=self.course_key, user_partitions={})
        ContentTypeGatingConfig.objects.create(enabled=False, studio_override_enabled=False)

        partition = create_content_gating_partition(mock_course)
        self.assertIsNone(partition)

    def test_create_content_gating_partition_no_scheme_installed(self):
        mock_course = Mock(id=self.course_key, user_partitions={})
        ContentTypeGatingConfig.objects.create(enabled=True, enabled_as_of=datetime(2018, 1, 1))

        with patch('openedx.features.content_type_gating.partitions.UserPartition.get_scheme', side_effect=UserPartitionError):
            partition = create_content_gating_partition(mock_course)

        self.assertIsNone(partition)

    def test_create_content_gating_partition_partition_id_used(self):
        mock_course = Mock(id=self.course_key, user_partitions={Mock(name='partition', id=CONTENT_GATING_PARTITION_ID): object()})
        ContentTypeGatingConfig.objects.create(enabled=True, enabled_as_of=datetime(2018, 1, 1))

        with patch('openedx.features.content_type_gating.partitions.LOG') as mock_log:
            partition = create_content_gating_partition(mock_course)
            mock_log.warning.assert_called()
        self.assertIsNone(partition)

    def test_access_denied_fragment_for_masquerading(self):
        """
        Test that a global staff sees gated content flag when viewing course as `Learner in Audit`
        Note: Global staff doesn't require to be enrolled in course.
        """
        mock_request = RequestFactory().get('/')
        mock_course = Mock(id=self.course_key, user_partitions={})
        mock_block = Mock(scope_ids=Mock(usage_id=Mock(course_key=mock_course.id)))
        mock_course_masquerade = Mock(
            role='student',
            user_partition_id=ENROLLMENT_TRACK_PARTITION_ID,
            group_id=settings.COURSE_ENROLLMENT_MODES['audit']['id'],
            user_name=None
        )
        CourseModeFactory.create(course_id=mock_course.id, mode_slug='verified')

        global_staff = GlobalStaffFactory.create()
        ContentTypeGatingConfig.objects.create(enabled=False, studio_override_enabled=True)

        partition = create_content_gating_partition(mock_course)

        with patch(
            'courseware.masquerade.get_course_masquerade',
            return_value=mock_course_masquerade
        ), patch(
            'openedx.features.content_type_gating.partitions.get_course_masquerade',
            return_value=mock_course_masquerade
        ), patch(
            'crum.get_current_request',
            return_value=mock_request
        ):
            fragment = partition.access_denied_fragment(mock_block, global_staff, 'test_group', 'test_allowed_group')

        self.assertIsNotNone(fragment)
