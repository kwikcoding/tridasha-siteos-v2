"""Import parser tests — no database.  python -m unittest apps.materials.tests.test_importer"""
import unittest
from datetime import date
from decimal import Decimal

from apps.materials import importer as imp

REGISTER_CSV = """HIGH-RISE MATERIALS REGISTER,,,,,,,,,,,,,,,
Filter by Trade,,,,,,,,,,,,,,,
Item ID,Trade,System / section,Material / equipment item,Unit,Specification to confirm,Applicability,Block / floor / zone,Required quantity,Approved size / grade / rating,Approved make,Vendor,Drawing / BOQ reference,Procurement status,Required-by date,Remarks / package inclusion
MAT-0001,Civil & Structure,Concrete,Ready mix concrete M25,cum,Grade and slump,Required,Tower A,"1,250",M25,Ultratech,,STR-01,Ordered,15-11-2026,
MAT-0002,Electrical,Cables,"FRLS copper cable, 4 sqmm",m,Cores and size,to review,,,,,,,,,
MAT-0003,Electrical,Cables,Armoured cable,m,,Maybe,,abc,,,,,,,
,,,,,,,,,,,,,,,
MAT-0001,Civil & Structure,Concrete,Duplicate,cum,,,,,,,,,,,
"""

CATALOGUE_CSV = """Item Code,Material Name,Category,UOM,Rate (₹),GST %,Reorder level
cem-53,OPC 53 Cement,Cement,bag,"₹ 410.50",28,200
STL-12,TMT bar 12 mm,Steel,kg,68,18,
,No code,Steel,kg,1,,
"""


class Register(unittest.TestCase):
    def setUp(self):
        self.res = imp.parse_register("register.csv", REGISTER_CSV.encode())

    def test_header_found_below_title_rows(self):
        self.assertEqual(self.res["columns"]["item"], "Material / equipment item")
        self.assertEqual(self.res["columns"]["req_qty"], "Required quantity")

    def test_values_converted(self):
        first = self.res["rows"][0]["data"]
        self.assertEqual(first["item_id"], "MAT-0001")
        self.assertEqual(first["req_qty"], Decimal("1250"))
        self.assertEqual(first["required_by"], date(2026, 11, 15))
        self.assertEqual(first["applicability"], "Required")
        self.assertEqual(first["status"], "Ordered")
        self.assertEqual(self.res["rows"][1]["data"]["applicability"], "To review")   # case-insensitive
        self.assertEqual(self.res["rows"][1]["data"]["item"], "FRLS copper cable, 4 sqmm")

    def test_errors_reported_per_line(self):
        self.assertEqual(len(self.res["rows"]), 2)
        lines = {e["line"]: e["message"] for e in self.res["errors"]}
        self.assertIn("Applicability", lines[6])
        self.assertIn("isn’t a number", lines[6])
        self.assertIn("Duplicate", lines[8])


class Catalogue(unittest.TestCase):
    def test_parse(self):
        res = imp.parse_catalogue("materials.csv", CATALOGUE_CSV.encode())
        self.assertEqual([r["data"]["code"] for r in res["rows"]], ["CEM-53", "STL-12"])
        self.assertEqual(res["rows"][0]["data"]["std_rate"], Decimal("410.50"))
        self.assertEqual(res["rows"][0]["data"]["unit"], "bag")
        self.assertEqual(res["errors"][0]["line"], 4)

    def test_xlsx_roundtrip(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.skipTest("openpyxl not installed")
        import io
        wb = Workbook()
        ws = wb.active
        ws.title = "Materials"
        ws.append(["Code", "Name", "Unit", "Rate"])
        ws.append(["A-1", "Sand", "cum", 1800])
        buf = io.BytesIO()
        wb.save(buf)
        res = imp.parse_catalogue("m.xlsx", buf.getvalue())
        self.assertEqual(res["rows"][0]["data"]["std_rate"], Decimal("1800"))

    def test_wrong_file(self):
        with self.assertRaises(imp.ImportError_):
            imp.parse_catalogue("x.pdf", b"%PDF")
        with self.assertRaises(imp.ImportError_):
            imp.parse_catalogue("x.csv", b"foo,bar\n1,2\n")


if __name__ == "__main__":
    unittest.main()
