"""
Soft Delete Infrastructure
==========================
Provides reusable mixins for soft-delete pattern:
  Active → Soft Delete (Archive) → Hard Delete (Permanent)

Usage (ViewSet):
    class MyViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
        # Make sure get_queryset filters is_deleted=False for the list action.
        ...

    This adds:
      - DELETE /{id}/          → soft-delete (archive)
      - GET  /archived/        → list archived records (paginated)
      - POST /{id}/restore/    → restore an archived record
      - DELETE /{id}/hard-delete/ → permanently delete an archived record
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response


# =========== VIEWSET MIXIN ===========


class SoftDeleteViewSetMixin:
    """
    ViewSet mixin that implements soft-delete / archive / hard-delete.

    Requirements on the model:
      - ``is_deleted`` BooleanField (default=False)
      - ``deleted_at`` DateTimeField (null=True, blank=True)

    The mixin does NOT override ``get_queryset()``.  Each ViewSet is
    responsible for filtering ``is_deleted=False`` in its own queryset
    (many already do).  The archive / restore / hard-delete actions
    build their own querysets so they can reach soft-deleted rows.
    """

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _get_model(self):
        """Return the model class from the queryset."""
        return self.get_queryset().model

    def _get_all_qs(self):
        """Return a queryset that includes soft-deleted rows."""
        model = self._get_model()
        if hasattr(model, "all_objects"):
            return model.all_objects.all()
        return model._default_manager.all()

    def _get_archived_instance(self, pk):
        """Fetch a single record (deleted or not) by pk, or 404."""
        return get_object_or_404(self._get_all_qs(), pk=pk)

    # ------------------------------------------------------------------
    # override destroy → soft-delete
    # ------------------------------------------------------------------
    def perform_destroy(self, instance):
        """Soft-delete: set is_deleted=True + deleted_at."""
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        update_fields = ["is_deleted", "deleted_at"]
        instance.save(update_fields=update_fields)

    # ------------------------------------------------------------------
    # extra actions
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="archived")
    def archived(self, request):
        """List all archived (soft-deleted) records, with pagination."""
        qs = self._get_all_qs().filter(is_deleted=True)
        qs = self.filter_queryset(qs)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        """Restore a soft-deleted record back to active."""
        instance = self._get_archived_instance(pk)
        if not instance.is_deleted:
            return Response(
                {"detail": "This record is not archived."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.is_deleted = False
        instance.deleted_at = None
        instance.save(update_fields=["is_deleted", "deleted_at"])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["delete"], url_path="hard-delete")
    def hard_delete(self, request, pk=None):
        """Permanently delete an archived record from the database."""
        instance = self._get_archived_instance(pk)
        if not instance.is_deleted:
            return Response(
                {"detail": "Record must be archived before it can be permanently deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
