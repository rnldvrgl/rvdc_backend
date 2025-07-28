from django.db import models
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from services.models import AirconInstallation
from utils.enums import (
    AirconType,
)
from django.core.exceptions import ValidationError
