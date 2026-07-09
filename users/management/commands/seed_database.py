from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.utils import IntegrityError
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Seed sample data across all local project models. "
        "This command first runs create_default_users, then tops up each model with sample rows. "
        "DEV/LOCAL USE ONLY — refuses to run when DEBUG=False."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--per-model",
            type=int,
            default=2,
            help="Minimum number of records to ensure per model.",
        )
        parser.add_argument(
            "--only-app",
            action="append",
            default=[],
            help="Seed only specific app labels (can be passed multiple times).",
        )
        parser.add_argument(
            "--skip-app",
            action="append",
            default=[],
            help="Skip specific app labels (can be passed multiple times).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build and validate sample payloads but do not save records.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "DANGEROUS: override the production safety guard and run anyway, "
                "even when DEBUG=False. Only use this if you are absolutely certain "
                "you want to inject sample data into this database."
            ),
        )

    def handle(self, *args, **options):
        # --- Production safety guard ---------------------------------------
        force = bool(options.get("force"))
        if not settings.DEBUG and not force:
            self.stdout.write(self.style.ERROR(
                "\n"
                "seed_database refused to run: DEBUG=False (this looks like production).\n"
                "This command injects fabricated sample data into every local model and\n"
                "is intended for local/dev environments only.\n\n"
                "If you are ABSOLUTELY sure you want to run this against the current\n"
                "database, re-run with --force. This is not recommended.\n"
            ))
            return

        if not settings.DEBUG and force:
            self.stdout.write(self.style.WARNING(
                "\n"
                "⚠️  --force passed with DEBUG=False. Proceeding anyway.\n"
                "⚠️  This WILL create fake sample rows in what appears to be production.\n"
            ))
        # ---------------------------------------------------------------------

        self.per_model = max(1, int(options["per_model"]))
        self.only_apps = set(options.get("only_app") or [])
        self.skip_apps = set(options.get("skip_app") or [])
        self.dry_run = bool(options.get("dry_run"))
        self.seed_started = timezone.now()
        self.max_attempts_per_row = 12

        self.created_by_model = {}
        self.errors = []

        self.stdout.write(self.style.WARNING("Running create_default_users before global seeding..."))
        try:
            call_command("create_default_users")
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f"create_default_users skipped/failed: {exc}")
            )

        local_models = self._collect_local_models()
        ordered_models = self._order_models_by_fk_dependencies(local_models)

        self.stdout.write(
            self.style.WARNING(
                f"Seeding {len(ordered_models)} models with target count {self.per_model} each..."
            )
        )

        for model in ordered_models:
            self._seed_model(model)

        total_created = sum(self.created_by_model.values())
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed run finished."))
        self.stdout.write(f"Models processed: {len(ordered_models)}")
        self.stdout.write(f"Rows created: {total_created}")

        if self.errors:
            self.stdout.write(self.style.WARNING(""))
            self.stdout.write(self.style.WARNING("Models with seed errors:"))
            for label, message in self.errors:
                self.stdout.write(self.style.WARNING(f"- {label}: {message}"))

    def _collect_local_models(self):
        local_app_labels = {
            app_label.split(".")[-1]
            for app_label in settings.INSTALLED_APPS
            if not app_label.startswith("django.")
            and app_label
            not in {
                "daphne",
                "rest_framework",
                "django_filters",
                "corsheaders",
                "rest_framework_simplejwt.token_blacklist",
                "channels",
            }
        }

        if self.only_apps:
            local_app_labels &= self.only_apps

        local_app_labels -= self.skip_apps

        models_to_seed = []
        for app_config in apps.get_app_configs():
            if app_config.label not in local_app_labels:
                continue
            for model in app_config.get_models():
                meta = model._meta
                if meta.abstract or meta.proxy or not meta.managed:
                    continue
                models_to_seed.append(model)

        return models_to_seed

    def _order_models_by_fk_dependencies(self, models_list):
        deps_map = {
            model: self._required_fk_dependencies(model, set(models_list))
            for model in models_list
        }

        ordered = []
        unresolved = set(models_list)

        while unresolved:
            progress = False
            for model in list(unresolved):
                if deps_map[model].issubset(set(ordered)):
                    ordered.append(model)
                    unresolved.remove(model)
                    progress = True
            if not progress:
                # Circular or complex dependencies; keep deterministic output.
                ordered.extend(sorted(unresolved, key=lambda m: m._meta.label_lower))
                break

        return ordered

    def _required_fk_dependencies(self, model, models_set):
        deps = set()
        for field in model._meta.get_fields():
            if not getattr(field, "is_relation", False) or field.many_to_many:
                continue
            if not getattr(field, "concrete", False):
                continue
            if getattr(field, "auto_created", False):
                continue
            if field.null or field.has_default() or getattr(field, "blank", False):
                continue
            related_model = field.related_model
            if related_model in models_set:
                deps.add(related_model)
        return deps

    @transaction.atomic
    def _seed_model(self, model):
        label = model._meta.label
        manager = model._default_manager

        existing = manager.count()
        if existing >= self.per_model:
            self.stdout.write(f"- {label}: already has {existing}, skipped")
            return

        to_create = self.per_model - existing
        created_count = 0

        for idx in range(to_create):
            row_seeded = False
            last_exc = None

            for attempt in range(self.max_attempts_per_row):
                seq = existing + created_count + idx + attempt
                try:
                    payload, m2m_values = self._build_payload(model, seq)
                    instance = model(**payload)

                    instance.full_clean(exclude=list(m2m_values.keys()))

                    if not self.dry_run:
                        instance.save()
                        for field_name, rel_objects in m2m_values.items():
                            getattr(instance, field_name).set(rel_objects)

                    created_count += 1
                    row_seeded = True
                    break
                except (ValidationError, IntegrityError, ValueError) as exc:
                    last_exc = exc
                    continue
                except Exception as exc:
                    last_exc = exc
                    break

            if not row_seeded:
                if last_exc is not None:
                    self.errors.append((label, str(last_exc)))
                break

        self.created_by_model[label] = self.created_by_model.get(label, 0) + created_count

        if created_count:
            mode = "validated" if self.dry_run else "created"
            self.stdout.write(self.style.SUCCESS(f"- {label}: {mode} {created_count}"))
        else:
            self.stdout.write(self.style.WARNING(f"- {label}: no rows added"))

    def _build_payload(self, model, idx):
        payload = {}
        m2m_values = {}

        for field in model._meta.get_fields():
            if getattr(field, "auto_created", False):
                continue

            if isinstance(field, models.ManyToManyField):
                related = field.related_model._default_manager.all()[:2]
                m2m_values[field.name] = list(related)
                continue

            if not isinstance(field, models.Field):
                continue

            if field.primary_key and isinstance(field, (models.AutoField, models.BigAutoField)):
                continue

            if not getattr(field, "editable", True):
                continue

            if field.has_default() or getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
                continue

            if field.name == "password":
                payload[field.name] = "pbkdf2_sha256$260000$sample$kP6tNn.3BfLl7XrP9lMwe1N8lWmFBxg6qN0zi1zqjPo="
                continue

            if isinstance(field, models.ForeignKey):
                related_instance = self._pick_related_instance(field, idx)
                if related_instance is None and not field.null:
                    raise ValueError(
                        f"Required relation '{field.name}' has no source rows in {field.related_model._meta.label}"
                    )
                payload[field.name] = related_instance
                continue

            if isinstance(field, models.OneToOneField):
                related_qs = self._related_queryset_for_field(field).exclude(
                    pk__in=model._default_manager.values_list(field.attname, flat=True)
                )
                related_items = list(related_qs[:50])
                related_instance = related_items[idx % len(related_items)] if related_items else None
                if related_instance is None and not field.null:
                    raise ValueError(
                        f"Required one-to-one '{field.name}' has no unused source rows in {field.related_model._meta.label}"
                    )
                payload[field.name] = related_instance
                continue

            value = self._sample_scalar_value(model, field, idx)
            if value is None and not field.null and not field.blank:
                raise ValueError(f"Could not infer required field '{field.name}'")
            payload[field.name] = value

        return payload, m2m_values

    def _sample_scalar_value(self, model, field, idx):
        if field.choices:
            return field.choices[0][0]

        unique_suffix = uuid4().hex[:8]
        model_key = model._meta.model_name
        field_name = field.name.lower()

        if isinstance(field, models.EmailField):
            return f"{model_key}_{field.name}_{unique_suffix}@example.com"
        if "contact" in field_name or "phone" in field_name or "mobile" in field_name:
            return self._sample_contact_number(idx, field.max_length)
        if field.name == "month_key":
            month_date = (self.seed_started.date().replace(day=1) + timedelta(days=idx * 31))
            month_date = month_date.replace(day=1)
            return month_date.strftime("%Y-%m")
        if isinstance(field, models.CharField):
            if field.unique:
                return self._short_unique_string(model_key, field.name, idx, field.max_length)
            base = f"{model_key}_{field.name}_{idx + 1}"
            return base[: field.max_length] if field.max_length else base
        if isinstance(field, models.SlugField):
            return self._short_unique_string(model_key, field.name, idx, field.max_length, sep="-")
        if isinstance(field, models.TextField):
            return f"Sample text for {model_key}.{field.name} #{idx + 1}"
        if isinstance(field, (models.IntegerField, models.BigIntegerField, models.SmallIntegerField, models.PositiveIntegerField, models.PositiveSmallIntegerField)):
            return idx + 1
        if isinstance(field, models.BooleanField):
            return True
        if isinstance(field, models.DecimalField):
            return self._sample_decimal_value(field, idx)
        if isinstance(field, models.FloatField):
            return 100.0
        if isinstance(field, models.DateTimeField):
            return self.seed_started + timedelta(minutes=idx)
        if isinstance(field, models.DateField):
            return self.seed_started.date() + timedelta(days=idx)
        if isinstance(field, models.TimeField):
            return time(hour=9, minute=0)
        if isinstance(field, models.DurationField):
            return timedelta(hours=1)
        if isinstance(field, models.UUIDField):
            return uuid4()
        if isinstance(field, models.URLField):
            return f"https://example.com/{model_key}/{field.name}/{idx + 1}"
        if isinstance(field, models.GenericIPAddressField):
            return "127.0.0.1"
        if isinstance(field, models.FileField):
            return f"sample_{model_key}_{idx + 1}.dat"
        if isinstance(field, models.JSONField):
            return {"sample": True, "model": model_key, "idx": idx + 1}
        if isinstance(field, models.BinaryField):
            return b"sample"

        if field.null:
            return None

        return None

    def _related_queryset_for_field(self, field):
        qs = field.related_model._default_manager.all()
        limit_choices = field.get_limit_choices_to()

        if isinstance(limit_choices, dict) and limit_choices:
            try:
                qs = qs.filter(**limit_choices)
            except Exception:
                pass
        elif isinstance(limit_choices, models.Q):
            try:
                qs = qs.filter(limit_choices)
            except Exception:
                pass

        return qs

    def _pick_related_instance(self, field, idx):
        qs = self._related_queryset_for_field(field)
        related_items = list(qs[:50])
        if not related_items:
            return None
        return related_items[idx % len(related_items)]

    def _sample_decimal_value(self, field, idx):
        scale = int(field.decimal_places or 0)
        max_digits = int(field.max_digits or 12)
        int_digits = max(1, max_digits - scale)
        step = Decimal("1").scaleb(-scale)
        max_abs = (Decimal(10) ** int_digits) - step

        value = Decimal(idx + 1)
        if value > max_abs:
            value = max_abs
        if scale:
            value = value.quantize(step)
        return value

    def _sample_contact_number(self, idx, max_length):
        raw = f"09{(idx + 1):09d}"
        if max_length:
            return raw[:max_length]
        return raw

    def _short_unique_string(self, model_key, field_name, idx, max_length, sep="_"):
        token = f"{idx + 1:x}{uuid4().hex[:4]}"
        head = f"{model_key}{sep}{field_name}{sep}"
        candidate = f"{head}{token}"

        if not max_length:
            return candidate
        if len(candidate) <= max_length:
            return candidate

        return token[-max_length:]
