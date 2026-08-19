from __future__ import annotations

import csv
from pathlib import Path


FIRST_NAME_STEMS = [
    "กิตติ",
    "จิรา",
    "ชย",
    "ณัฐ",
    "ธน",
    "นภ",
    "ปริญ",
    "พงศ",
    "ภัทร",
    "วร",
]
FIRST_NAME_ENDINGS = [
    "กร",
    "กานต์",
    "ชัย",
    "ณัฐ",
    "ภัทร",
    "เมธ",
    "รัตน์",
    "วดี",
    "วุฒิ",
    "ศักดิ์",
]
LAST_NAME_STEMS = [
    "กุล",
    "จันทร์",
    "ชัย",
    "ตั้ง",
    "ธรรม",
    "บุญ",
    "พัฒนา",
    "รัตน",
    "วงศ์",
    "ศรี",
]
LAST_NAME_ENDINGS = [
    "กิจ",
    "เกษม",
    "เจริญ",
    "ประเสริฐ",
    "รักษ์",
    "รุ่งเรือง",
    "วัฒนะ",
    "สวัสดิ์",
    "สุข",
    "ไพศาล",
]

FIRST_NAMES = [
    f"{stem}{ending}" for stem in FIRST_NAME_STEMS for ending in FIRST_NAME_ENDINGS
]
LAST_NAMES = [
    f"{stem}{ending}" for stem in LAST_NAME_STEMS for ending in LAST_NAME_ENDINGS
]

LOCATIONS = [
    ("สุขุมวิท", "คลองเตย", "กรุงเทพมหานคร", "10110"),
    ("พหลโยธิน", "จตุจักร", "กรุงเทพมหานคร", "10900"),
    ("รัชดาภิเษก", "ห้วยขวาง", "กรุงเทพมหานคร", "10310"),
    ("ลาดพร้าว", "บางกะปิ", "กรุงเทพมหานคร", "10240"),
    ("เพชรเกษม", "ภาษีเจริญ", "กรุงเทพมหานคร", "10160"),
    ("นิมมานเหมินท์", "เมืองเชียงใหม่", "เชียงใหม่", "50200"),
    ("ห้วยแก้ว", "เมืองเชียงใหม่", "เชียงใหม่", "50300"),
    ("เชียงใหม่-ลำพูน", "สารภี", "เชียงใหม่", "50140"),
    ("มิตรภาพ", "เมืองขอนแก่น", "ขอนแก่น", "40000"),
    ("ศรีจันทร์", "เมืองขอนแก่น", "ขอนแก่น", "40000"),
    ("เทพกระษัตรี", "เมืองภูเก็ต", "ภูเก็ต", "83000"),
    ("ปฏัก", "กะรน", "ภูเก็ต", "83100"),
    ("ราษฎร์อุทิศ", "หาดใหญ่", "สงขลา", "90110"),
    ("กาญจนวนิช", "เมืองสงขลา", "สงขลา", "90000"),
    ("บรมไตรโลกนารถ", "เมืองพิษณุโลก", "พิษณุโลก", "65000"),
    ("เอกาทศรถ", "เมืองพิษณุโลก", "พิษณุโลก", "65000"),
    ("สืบศิริ", "เมืองนครราชสีมา", "นครราชสีมา", "30000"),
    ("มุขมนตรี", "เมืองนครราชสีมา", "นครราชสีมา", "30000"),
    ("นครอินทร์", "เมืองนนทบุรี", "นนทบุรี", "11000"),
    ("รัตนาธิเบศร์", "บางบัวทอง", "นนทบุรี", "11110"),
    ("ศรีนครินทร์", "เมืองสมุทรปราการ", "สมุทรปราการ", "10270"),
    ("สุขุมวิท", "บางละมุง", "ชลบุรี", "20150"),
    ("พระยาสัจจา", "เมืองชลบุรี", "ชลบุรี", "20000"),
    ("นเรศวร", "พระนครศรีอยุธยา", "พระนครศรีอยุธยา", "13000"),
    ("โรจนะ", "อุทัย", "พระนครศรีอยุธยา", "13210"),
    ("พหลโยธิน", "เมืองเชียงราย", "เชียงราย", "57000"),
    ("ธนาลัย", "เมืองเชียงราย", "เชียงราย", "57000"),
    ("ท่าเมือง", "เมืองกาญจนบุรี", "กาญจนบุรี", "71000"),
    ("หน้าเมือง", "เมืองราชบุรี", "ราชบุรี", "70000"),
    ("ชนเกษม", "เมืองสุราษฎร์ธานี", "สุราษฎร์ธานี", "84000"),
]

ROW_COUNT = 10_000


def build_rows() -> list[dict[str, str | int]]:
    rows = []
    for index in range(ROW_COUNT):
        first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
        last_name = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
        street, district, province, postal_code = LOCATIONS[
            (index * 17) % len(LOCATIONS)
        ]
        house_number = f"{index + 1}/{index % 19 + 1}"
        address = (
            f"{house_number} ถนน{street} อำเภอ{district} "
            f"จังหวัด{province} {postal_code}"
        )
        rows.append(
            {
                "id": index + 1,
                "first_name": first_name,
                "last_name": last_name,
                "street": street,
                "district": district,
                "province": province,
                "postal_code": postal_code,
                "address": address,
            }
        )
    return rows


def main() -> None:
    output_path = Path(__file__).with_name("thai_people.csv")
    fieldnames = [
        "id",
        "first_name",
        "last_name",
        "street",
        "district",
        "province",
        "postal_code",
        "address",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(build_rows())
    print(f"Created {output_path} with {ROW_COUNT:,} varied records")


if __name__ == "__main__":
    main()
