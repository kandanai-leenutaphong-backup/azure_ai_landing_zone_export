export type Reference = {
  id: string;
  name: string;
  group: "Atmosphere" | "Structure" | "Archive";
  state: "Reviewed" | "Needs review" | "Pending";
  records: number;
  date: string;
  owner: string;
};

export const references: Reference[] = [
  { id: "AS-0001", name: "Cirrus array", group: "Atmosphere", state: "Reviewed", records: 12408, date: "2026-09-09", owner: "Mira Chen" },
  { id: "AS-0002", name: "Stratus relay", group: "Structure", state: "Needs review", records: 8361, date: "2026-09-08", owner: "Eli Torres" },
  { id: "AS-0003", name: "Cumulus archive", group: "Archive", state: "Reviewed", records: 24506, date: "2026-09-08", owner: "Ada Brooks" },
  { id: "AS-0004", name: "North platform", group: "Structure", state: "Pending", records: 3412, date: "2026-09-07", owner: "Mira Chen" },
  { id: "AS-0005", name: "Upper atmosphere", group: "Atmosphere", state: "Reviewed", records: 18732, date: "2026-09-07", owner: "Eli Torres" },
  { id: "AS-0006", name: "Long-horizon-observation-reference-2026-09-06", group: "Archive", state: "Needs review", records: 92714, date: "2026-09-06", owner: "Ada Brooks" },
  { id: "AS-0007", name: "Eastward passage", group: "Atmosphere", state: "Pending", records: 0, date: "2026-09-06", owner: "Mira Chen" },
  { id: "AS-0008", name: "Sapphire channel", group: "Structure", state: "Reviewed", records: 6712, date: "2026-09-05", owner: "Eli Torres" },
  { id: "AS-0009", name: "Cloudbreak station", group: "Structure", state: "Reviewed", records: 51608, date: "2026-09-04", owner: "Ada Brooks" },
  { id: "AS-0010", name: "Distant formation", group: "Atmosphere", state: "Pending", records: 1108, date: "2026-09-03", owner: "Mira Chen" },
  { id: "AS-0011", name: "Southern archive", group: "Archive", state: "Reviewed", records: 46327, date: "2026-09-02", owner: "Eli Torres" },
  { id: "AS-0012", name: "Horizon metadata", group: "Archive", state: "Needs review", records: 9201, date: "2026-09-01", owner: "Ada Brooks" },
];

export const trend = [
  { time: "06:00", upper: 22, lower: 13 }, { time: "07:00", upper: 32, lower: 18 },
  { time: "08:00", upper: 28, lower: 16 }, { time: "09:00", upper: 53, lower: 22 },
  { time: "10:00", upper: 46, lower: 30 }, { time: "11:00", upper: 70, lower: 33 },
  { time: "12:00", upper: 59, lower: 28 }, { time: "13:00", upper: 84, lower: 40 },
  { time: "14:00", upper: 73, lower: 46 }, { time: "15:00", upper: 91, lower: 43 },
  { time: "16:00", upper: 80, lower: 50 }, { time: "17:00", upper: 96, lower: 54 },
];