"""
Management command to delete unused profile images to save disk space.
This will delete profile images that are not referenced by any user.
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from users.models import CustomUser


class Command(BaseCommand):
    help = 'Delete unused profile images to save disk space'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview files to be deleted without actually deleting them'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get the profile images directory
        profile_images_dir = os.path.join(settings.MEDIA_ROOT, 'profile_images')
        
        if not os.path.exists(profile_images_dir):
            self.stdout.write(
                self.style.WARNING(f'Profile images directory not found: {profile_images_dir}')
            )
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== DRY RUN MODE - No files will be deleted ===\n'))
        
        # Get all profile image filenames from database
        users_with_images = CustomUser.all_objects.exclude(
            profile_image__isnull=True
        ).exclude(
            profile_image=''
        )
        
        used_filenames = set()
        for user in users_with_images:
            if user.profile_image:
                # Extract just the filename from the path
                filename = os.path.basename(user.profile_image.name)
                used_filenames.add(filename)
        
        self.stdout.write(f'Found {len(used_filenames)} profile images in database')
        
        # Get all files in the profile_images directory
        all_files = []
        try:
            all_files = [f for f in os.listdir(profile_images_dir) 
                        if os.path.isfile(os.path.join(profile_images_dir, f))]
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error reading directory: {e}')
            )
            return
        
        self.stdout.write(f'Found {len(all_files)} files in profile_images directory\n')
        
        # Find unused files
        unused_files = [f for f in all_files if f not in used_filenames]
        
        if not unused_files:
            self.stdout.write(
                self.style.SUCCESS('No unused profile images found. All files are in use!')
            )
            return
        
        # Calculate total size of unused files
        total_size = 0
        for filename in unused_files:
            filepath = os.path.join(profile_images_dir, filename)
            try:
                total_size += os.path.getsize(filepath)
            except OSError:
                pass
        
        # Convert bytes to human-readable format
        def format_bytes(bytes_size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_size < 1024.0:
                    return f"{bytes_size:.2f} {unit}"
                bytes_size /= 1024.0
            return f"{bytes_size:.2f} TB"
        
        self.stdout.write(
            self.style.WARNING(
                f'Found {len(unused_files)} unused profile images '
                f'({format_bytes(total_size)} total)\n'
            )
        )
        
        # Delete or list unused files
        deleted_count = 0
        failed_count = 0
        
        for filename in unused_files:
            filepath = os.path.join(profile_images_dir, filename)
            file_size = 0
            
            try:
                file_size = os.path.getsize(filepath)
            except OSError:
                pass
            
            if dry_run:
                self.stdout.write(
                    f'  Would delete: {filename} ({format_bytes(file_size)})'
                )
                deleted_count += 1
            else:
                try:
                    os.remove(filepath)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  Deleted: {filename} ({format_bytes(file_size)})'
                        )
                    )
                    deleted_count += 1
                except OSError as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  Failed to delete {filename}: {e}'
                        )
                    )
                    failed_count += 1
        
        # Summary
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN SUMMARY:'))
            self.stdout.write(f'  Would delete: {deleted_count} files')
            self.stdout.write(f'  Total space to free: {format_bytes(total_size)}')
        else:
            self.stdout.write(self.style.SUCCESS('CLEANUP COMPLETE:'))
            self.stdout.write(self.style.SUCCESS(f'  Deleted: {deleted_count} files'))
            if failed_count > 0:
                self.stdout.write(self.style.ERROR(f'  Failed: {failed_count} files'))
            self.stdout.write(self.style.SUCCESS(f'  Space freed: {format_bytes(total_size)}'))
        
        self.stdout.write(f'  Files in use: {len(used_filenames)}')
        self.stdout.write('='*60)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\nRun without --dry-run to actually delete unused files'
                )
            )
