#!/bin/bash
# EHR Africa — Outreach Field App (Linux/Mac)
echo ""
echo "================================================"
echo "  EHR Africa — Outreach Field Application"
echo "  Running on: http://localhost:8765"
echo "  Open your browser to: http://localhost:8765"
echo "================================================"
echo ""

cd "$(dirname "$0")/.."

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run migrations
echo "Running database setup..."
python manage.py migrate --settings=outreach_field.settings_field --run-syncdb 2>/dev/null

# Create default admin if needed
python manage.py shell --settings=outreach_field.settings_field -c "
from apps.accounts.models import User
if not User.objects.filter(username='field_admin').exists():
    u = User.objects.create_superuser('field_admin', '', 'field123')
    u.role = 'super_admin'
    u.save()
    print('Default login: field_admin / field123')
" 2>/dev/null

echo ""
echo "Starting field server..."
echo "Press Ctrl+C to stop."
echo ""

# Try to open browser
which xdg-open &>/dev/null && xdg-open http://localhost:8765 &
which open &>/dev/null && open http://localhost:8765 &

python manage.py runserver 8765 --settings=outreach_field.settings_field --noreload
