# Manual Test Guide — Shopify Fulfillment Tool

**Version tested:** 1.8.9.6+
**Profiles:** StyleHub (fashion), BeautyBox (cosmetics + lot tracking)
**Test files location:** `data/manual_test/`

Each test order has its expected outcome written in the **Notes** field.
Results marked with `[internal]` appear in the `Internal_Tags` column (JSON array).
Results marked with `[tag]` appear in the `Status_Note` column.

---

## 1. Setup — Adding Test Profiles

1. Launch the application (`python gui_main.py`)
2. In the **Client Sidebar**, click **+ New Client**
3. For Profile 1: enter name `StyleHub`, ID `STYLEHUB`
4. Copy `data/manual_test/profile_1_stylehub/shopify_config.json` to the client's server folder
5. Copy `data/manual_test/profile_1_stylehub/client_config.json` to the client's server folder
6. Repeat for Profile 2: name `BeautyBox`, ID `BEAUTYBOX`
7. **Verify:** Both clients appear in the sidebar with their configured colors (blue / pink)

---

## 2. Loading Test Data

For **each profile separately:**

1. Select the client from the sidebar
2. Click **New Session** in the toolbar
3. Click **Load Orders** → select `orders_test.csv` from the profile folder
4. Click **Load Stock** → select `stock_test.csv` from the profile folder
5. Click **Run Analysis**
6. Wait for analysis to complete (green status in toolbar)

---

## 3. StyleHub — Scenario Checklist

**Expected totals after analysis: 9 Fulfillable, 3 Not Fulfillable**

| # | Order | Expected Status | Expected Tags (Status_Note) | Expected Internal Tags | Verify |
|---|-------|-----------------|----------------------------|------------------------|--------|
| 1 | #SH1001 | ✅ Fulfillable | — | — | Single item, PostOne, no rules |
| 2 | #SH1002 | ❌ Not Fulfillable | — | — | STH-SHORTS-L stock=0 |
| 3 | #SH1003 | ✅ Fulfillable | EXPRESS-DELIVERY | MULTI-ITEM | DHL Express, 2 items |
| 4 | #SH1004 | ✅ Fulfillable | — | MULTI-ITEM | SHIRT-L exact match (qty=stock=3) |
| 5 | #SH1005 | ✅ Fulfillable | EXPRESS-DELIVERY | MULTI-ITEM | Multi processed first; DHL Standard |
| 6 | #SH1006 | ❌ Not Fulfillable | — | — | HOODIE-M=2 needed; only 1 left after SH1005 |
| 7 | #SH1007 | ✅ Fulfillable | — | MULTI-ITEM | SET-SUMMER decoded (SHIRT-M + SHORTS-M) |
| 8 | #SH1008 | ❌ Not Fulfillable | — | MULTI-ITEM | SET-WINTER decoded; JACKET-L=0 |
| 9 | #SH1009 | ✅ Fulfillable | HIGH-VALUE | — | Total=250 > 200 triggers R3 |
| 10 | #SH1010 | ✅ Fulfillable | VIP-PRIORITY | — | Tags=VIP triggers R4 |
| 11 | #SH1011 | ✅ Fulfillable | EXPRESS-DELIVERY | DE-ORDER | Germany + DHL triggers R1+R2 |
| 12 | #SH1012 | ✅ Fulfillable | BULK-QTY | — | qty=10 > 5 triggers R5 |

**How to verify tags:**
- Show the `Status_Note` column (Configure Columns if hidden)
- Show the `Internal_Tags` column
- Check `Order_Type` column: SH1003, SH1004, SH1005, SH1007, SH1008 must show `Multi`

**SET decoding verification (SH1007, SH1008):**
- SH1007 should appear as **2 rows** in the table (SHIRT-M + SHORTS-M) under order #SH1007
- SH1008 should appear as **3 rows** (JACKET-L + PANTS-L + SCARF-OS) under order #SH1008

**Box assignment verification:**
- Show `Order_Min_Box` column
- SH1001 (SHIRT-M x2, ~400g) → should show `BOX-S`
- SH1005 (HOODIE-M + SHIRT-S, ~780g) → should show `BOX-S`
- SH1008 (decoded: JACKET-L + PANTS-L + SCARF-OS, ~1550g) → should show `BOX-S` or `BOX-M`

---

## 4. BeautyBox — Scenario Checklist

**Expected totals after analysis: 10 Fulfillable, 2 Not Fulfillable**

| # | Order | Expected Status | Expected Tags (Status_Note) | Expected Internal Tags | Verify |
|---|-------|-----------------|----------------------------|------------------------|--------|
| 1 | #BB2001 | ✅ Fulfillable | — | — | FIFO from LOT-2024-001 |
| 2 | #BB2002 | ✅ Fulfillable | — | — | Multi-lot span (LOT-2024-001 + LOT-2025-001) |
| 3 | #BB2003 | ❌ Not Fulfillable | — | — | GLOSS-PINK stock=0 |
| 4 | #BB2004 | ✅ Fulfillable | DHL-EXPRESS | multi-item | DHL Express courier |
| 5 | #BB2005 | ✅ Fulfillable | HIGH-VALUE, HANDLE-WITH-CARE | vip, multi-item | Total=580 + Tags=FRAGILE |
| 6 | #BB2006 | ✅ Fulfillable | BULK-ORDER | — | qty=25 > 20 |
| 7 | #BB2007 | ✅ Fulfillable | GIFT-PACKAGING | — | SKU contains "GIFT" |
| 8 | #BB2008 | ✅ Fulfillable | — | UA-LOCAL, multi-item | CREAM crosses 2 lots; Ukraine country |
| 9 | #BB2009 | ✅ Fulfillable | — | multi-item | Both items in stock |
| 10 | #BB2010 | ❌ Not Fulfillable | — | multi-item | GLOSS-PINK=0; all-or-nothing blocks entire order |
| 11 | #BB2011 | ✅ Fulfillable | URGENT | — | Notes contains "urgent" |
| 12 | #BB2012 | ✅ Fulfillable | DHL-EXPRESS | multi-item | BB-STARTER-KIT decoded (3 components) |

**FIFO lot allocation verification (BB2002):**
- Generate packing list for BB2002's session
- In the packing list XLSX, BB-SERUM-30 for order #BB2002 should appear as **2 rows**:
  - Row 1: Lot=LOT-2024-001, Qty=10 (or however many remain after prior orders)
  - Row 2: Lot=LOT-2025-001, Qty=8 (remainder)
- This confirms FIFO multi-lot spanning works

**Two-action rule verification (BB2005):**
- `Status_Note` column must show: `HIGH-VALUE, HANDLE-WITH-CARE`
- `Internal_Tags` column must show: `["vip", "multi-item"]`
- Total=580 triggered R2 (both ADD_TAG and ADD_INTERNAL_TAG in one rule)
- Tags=FRAGILE triggered R3 (separate ADD_TAG action)

**SET decoding verification (BB2012):**
- #BB2012 should appear as **3 rows** (SERUM-30 + CREAM-50 + TONER-100) under order #BB2012

---

## 5. Packing List Verification

### StyleHub — DHL Orders Only packing list

1. In Analysis Results tab, click **Packing List** button
2. Select the config **"DHL Orders Only"** (filter: Shipping_Provider == DHL)
3. Generate and open the resulting XLSX
4. **Verify:** Only orders SH1003, SH1005, SH1011, SH1012 appear
   - SH1003: DHL Express ✓
   - SH1005: DHL Standard ✓
   - SH1011: DHL International ✓
   - SH1012: PostOne ← must NOT appear
5. **Verify:** Non-fulfillable orders are not included

### BeautyBox — Nova Poshta packing list

1. Click **Packing List** → select **"Nova Poshta Orders"**
2. **Verify:** Only BB2001, BB2005, BB2008, BB2011 appear
3. **Verify:** BB2008's CREAM-50 shows as 2 rows (lot split)

### All Orders packing list (both profiles)

1. Select **"All Fulfillable Orders"** config
2. **Verify:** All fulfillable orders are present, no Not Fulfillable orders

---

## 6. Settings Window Verification

### StyleHub Settings

1. Click **Settings** button → confirm Settings window opens
2. **Rules tab:** verify 6 rules listed in order:
   - R1: Tag DHL orders as EXPRESS-DELIVERY (priority 1)
   - R2: Tag Germany orders with internal tag (priority 2)
   - R3: Tag high-value orders (Total > 200) (priority 3)
   - R4: Tag VIP customer orders (priority 4)
   - R5: Tag bulk quantity lines (qty > 5) (priority 5)
   - R6: Tag multi-item orders with internal tag (priority 6)
3. **Couriers tab:** verify DHL, DPD, Speedy, PostOne listed
4. **Tag Categories tab:** verify 4 categories: Shipping, Priority, Handling, Status
5. **Sets tab (set_decoders):** verify STH-SET-SUMMER and STH-SET-WINTER listed
6. **Weight/Dimensions tab:** verify product and box entries loaded

### BeautyBox Settings

1. **Rules tab:** verify 8 rules listed (R1–R8 as in shopify_config.json)
2. **Column Mappings → Stock tab:** verify Годност → Expiry_Date and Партида → Batch are mapped
3. **Couriers tab:** verify DHL, Nova Poshta, Meest, Justin listed
4. **Sets tab:** verify BB-STARTER-KIT listed with 3 components

---

## 7. Column Toggle — Persistence Test

1. Open StyleHub analysis results
2. Click **Configure Columns** button
3. Hide the column `Order_Volumetric_Weight`
4. Hide the column `SKU_Volumetric_Weight`
5. Click Save
6. **Verify:** Columns disappear from table immediately
7. Close the session tab and re-open the session
8. **Verify:** The hidden columns remain hidden (persisted to client_config.json)
9. Restore: re-open Configure Columns → Show All → Save

---

## 8. Bulk Operations Test

1. In Analysis Results, enable **Bulk Mode** (toggle button)
2. Select 3 fulfillable orders using checkboxes
3. Click **Set Not Fulfillable**
4. **Verify:** All 3 selected orders change to red / Not Fulfillable status
5. Click **Set Fulfillable**
6. **Verify:** All 3 orders return to green / Fulfillable status
7. With orders still selected, click **Add Tag** → type `MANUAL-TEST` → confirm
8. **Verify:** `Status_Note` column shows `MANUAL-TEST` for all 3 selected orders
9. Click **Remove Tag** → select `MANUAL-TEST` → confirm
10. **Verify:** Tag removed from all 3 orders

---

## 9. Undo Test

1. Select order **#SH1001** (Fulfillable)
2. Right-click → **Set as Not Fulfillable** (or use bulk mode with 1 order)
3. **Verify:** SH1001 shows as Not Fulfillable
4. Click **Undo** button in toolbar
5. **Verify:** SH1001 reverts to Fulfillable
6. **Verify:** Undo button becomes disabled (nothing left to undo)

---

## 10. Session Browser Test

1. Click the **Sessions** tab (Tab 1)
2. **Verify:** The session you just created appears in the table
3. **Verify columns:** Session Name (date_N format), Status=active, Orders count, Items count, Fulfillable count
4. For StyleHub: Orders=12, Fulfillable=9, Not Fulfillable=3 (before any manual changes)
5. For BeautyBox: Orders=12, Fulfillable=10, Not Fulfillable=2
6. Double-click the session row → **Verify:** switches to Analysis Results tab with data loaded
7. Use the **Status filter** dropdown → select `Completed` → verify session disappears
8. Switch back to `All` → session reappears

---

## 11. Theme Toggle Test

1. Click the **Theme Toggle** button in the toolbar (sun/moon icon)
2. **Verify:** Application switches to dark theme
3. Check every UI area for **hardcoded grey colors** — there must be none
   - All text must use theme variables (white/light on dark background)
   - Table rows, headers, borders must all be themed
4. Toggle back to light theme
5. **Verify:** Application returns to light theme cleanly

---

## 12. Filter & Search Test (Analysis Results)

1. With StyleHub analysis loaded, click the **Search** field (Ctrl+F)
2. Type `DHL` → **Verify:** only orders with DHL in any column are shown (SH1003, SH1005, SH1011)
3. Clear filter → **Verify:** all 12 orders visible again
4. Use **Tag Filter** dropdown → select `EXPRESS-DELIVERY`
5. **Verify:** only tagged orders visible (SH1003, SH1005, SH1011)
6. Clear → all orders return

---

## Known Expected Counts Summary

| Profile | Total Orders | Fulfillable | Not Fulfillable | Rules Fired |
|---------|-------------|-------------|-----------------|-------------|
| StyleHub | 12 | 9 | 3 | R1×3, R2×1, R3×1, R4×1, R5×1, R6×5 |
| BeautyBox | 12 | 10 | 2 | R1×2, R2×1, R3×1, R4×1, R5×4, R6×1, R7×1, R8×6 |

---

## Stock Quantity Reference (for manual verification)

### StyleHub — Initial stock / After analysis

| SKU | Initial | Consumed | Remaining |
|-----|---------|----------|-----------|
| STH-SHIRT-S | 15 | 12 (SH1005:1 + SH1011:1 + SH1012:10) | 3 |
| STH-SHIRT-M | 8 | 5 (SH1003:1 + SH1007:1 + SH1001:2 + SH1004... wait) | see note |
| STH-SHIRT-L | 3 | 3 (SH1004) | 0 |
| STH-SHORTS-M | 12 | 5 (SH1003:1 + SH1004:2 + SH1007:1 ... ) | see note |
| STH-SHORTS-L | 0 | 0 | 0 |
| STH-JACKET-L | 0 | 0 (SH1008 fails) | 0 |
| STH-HOODIE-M | 2 | 1 (SH1005) | 1 |
| STH-DRESS-M | 6 | 1 (SH1009) | 5 |
| STH-LEGGINGS-S | 10 | 1 (SH1010) | 9 |

### BeautyBox — Initial lots / After analysis

| SKU | Lot | Initial | Consumed by | Remaining |
|-----|-----|---------|-------------|-----------|
| BB-SERUM-30 | LOT-2024-001 | 20 | BB2004(2), BB2012(1), BB2001(5), BB2002(12) | 0 |
| BB-SERUM-30 | LOT-2025-001 | 15 | BB2002(6) | 9 |
| BB-CREAM-50 | LOT-2024-002 | 10 | BB2004(5), BB2008(5) | 0 |
| BB-CREAM-50 | LOT-2025-002 | 25 | BB2008(5), BB2012(1), BB2011(1) | 18 |
| BB-TONER-100 | LOT-2024-003 | 8 | BB2005(1), BB2012(1) | 6 |
| BB-MASK-SET | LOT-2024-004 | 5 | BB2009(3) | 2 |
| BB-GLOSS-RED | LOT-2025-003 | 30 | BB2008(3), BB2006(25) | 2 |
| BB-GLOSS-PINK | LOT-2025-004 | 0 | — | 0 |
| BB-PERFUME-50 | LOT-2024-005 | 12 | BB2005(1), BB2009(5) | 6 |
| BB-GIFT-SET-A | LOT-2025-005 | 3 | BB2007(1) | 2 |
