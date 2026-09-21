"""
Generate sample signature images for all active staff users.

Usage:
    python manage.py generate_sample_signatures          # all active staff
    python manage.py generate_sample_signatures --user admin   # single user

Creates a PNG with the user's name rendered in a handwriting-style font
and saves it to the user's `signature` ImageField (media/staff/signatures/).
Existing signatures are skipped unless --force is used.
"""
import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.accounts.models import User


def _make_signature_image(full_name):
    """
    Generate a transparent-background PNG with the person's name
    rendered in a bold, signature-like style — large enough to be
    clearly visible on printed PDF reports.
    Returns bytes of the PNG.
    """
    from PIL import Image, ImageDraw, ImageFont

    width, height = 600, 160
    img = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Try common handwriting / italic fonts; fall back to default
    font = None
    font_size = 52
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',   # Linux (server)
        '/usr/share/fonts/truetype/freefont/FreeMonoOblique.ttf',     # Linux alt
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf',
        'Segoe Script',        # Windows
        'Palace Script MT',    # Windows
        'Lucida Handwriting',  # Windows
        'Comic Sans MS',       # Windows fallback
    ]
    for candidate in candidates:
        try:
            font = ImageFont.truetype(candidate, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    # Draw the name with dark navy-blue ink — fully opaque for clarity
    ink = (10, 20, 70, 255)
    bbox = draw.textbbox((0, 0), full_name, font=font)
    text_h = bbox[3] - bbox[1]
    text_w = bbox[2] - bbox[0]
    y = (height - text_h) // 2 - 8
    draw.text((24, y), full_name, fill=ink, font=font)

    # Bold effect — draw again offset by 1px
    draw.text((25, y), full_name, fill=ink, font=font)

    # Add a visible signature underline
    line_y = y + text_h + 10
    draw.line([(22, line_y), (28 + text_w, line_y)], fill=(10, 20, 70, 180), width=2)

    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


class Command(BaseCommand):
    help = 'Generate sample signature images for staff users'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Username to generate for (default: all active staff)')
        parser.add_argument('--force', action='store_true', help='Overwrite existing signatures')

    def handle(self, *args, **options):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.stderr.write(self.style.ERROR(
                'Pillow is required: pip install Pillow'
            ))
            return

        qs = User.objects.filter(is_active=True)
        if options['user']:
            qs = qs.filter(username=options['user'])

        created = 0
        skipped = 0
        for user in qs:
            if user.signature and not options['force']:
                skipped += 1
                continue

            name = user.get_full_name() or user.username
            png_bytes = _make_signature_image(name)
            filename = f'sig_{user.username}.png'
            user.signature.save(filename, ContentFile(png_bytes), save=True)
            created += 1
            self.stdout.write(f'  Created signature for {user.username} ({name})')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone — {created} created, {skipped} skipped (already have signature).'
        ))
