"""
Django admin command to populate expiry_date for approved verifications in SoftwareSecurePhotoVerification
"""
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from lms.djangoapps.verify_student.models import SoftwareSecurePhotoVerification

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    This command sets the expiry_date for users for which the verification is approved

    The task is performed in batches with maximum number of rows to process given in argument `batch_size`
    and a sleep time between each batch given by `sleep_time`

    Default values:
        `batch_size` = 1000 rows
        `sleep_time` = 10 seconds

    Example usage:
        $ ./manage.py lms populate_expiry_date --batch_size=1000 --sleep_time=5
    OR
        $ ./manage.py lms populate_expiry_date
    """
    help = 'Populate expiry_date for approved verifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch_size',
            action='store',
            dest='batch_size',
            type=int,
            default=1000,
            help='Maximum number of database rows to process. '
                 'This helps avoid locking the database while updating large amount of data.')
        parser.add_argument(
            '--sleep_time',
            action='store',
            dest='sleep_time',
            type=int,
            default=10,
            help='Sleep time in seconds between update of batches')

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.sspv = SoftwareSecurePhotoVerification.objects.filter(status='approved',
                                                                   expiry_date__isnull=True
                                                                   ).order_by('user_id')

    def handle(self, *args, **options):
        """
        Handler for the command

        It creates batches of approved Software Secure Photo Verification depending on the batch_size
        given as argument. Then for each distinct user in that batch it finds the most recent approved
        verification and set its expiry_date
        """
        batch_size = options['batch_size']
        sleep_time = options['sleep_time']

        try:
            max_user_id = self.sspv.last().user_id
            batch_start = self.sspv.first().user_id
            batch_stop = batch_start + batch_size
        except AttributeError:
            logger.info("AttributeError: No approved entries found in SoftwareSecurePhotoVerification")
            return

        while batch_start <= max_user_id:
            batch_queryset = self.sspv.filter(user_id__gte=batch_start, user_id__lt=batch_stop)
            users = batch_queryset.values('user_id').distinct()

            for user in users:
                recent_verification = self.find_recent_verification(user['user_id'])
                recent_verification.expiry_date = recent_verification.updated_at + timedelta(
                    days=settings.VERIFY_STUDENT["DAYS_GOOD_FOR"])
                recent_verification.save()

            if batch_stop < max_user_id:
                time.sleep(sleep_time)

            batch_start = batch_stop
            batch_stop += batch_size

    def find_recent_verification(self, user_id):
        """
        Returns the most recent approved verification for a user
        """
        return self.sspv.filter(user_id=user_id).latest('updated_at')
