"""Create a unique synthetic browser fixture. Never employee acceptance data."""
from pathlib import Path
from uuid import uuid4
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root / 'apps/engine'))
from tests.fixtures import write_attendance
output = root / 'storage/synthetic-browser.xls'
output.parent.mkdir(exist_ok=True)
write_attendance(output,marker=uuid4().hex)
print('Synthetic browser fixture ready in ignored storage/')
