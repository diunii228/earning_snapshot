from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from jobs.fs_kpi_shared import safe_float as _safe_float
try:
    from extractors.pdf_bctc.gemini_extractor import FinancialExtractor as InternalFinancialExtractor
except Exception:
    InternalFinancialExtractor = None

logger = logging.getLogger(__name__)


DEFAULT_EXTRACTOR_ROOT = Path("/Users/ddlyy/Downloads/New_Extract_2feb/base64_BCTC_Extraction")
DEFAULT_PDF_DIR = Path("/Users/ddlyy/Downloads/New_Extract_2feb/base64_BCTC_Extraction/temp_batch_downloads")
MANIFEST_PATH = Path("outputs/bctc_ingestion_manifest.json")


KPI_REQUESTS: List[Dict[str, Any]] = [
    # ── Profitability P&L items — cần both current & previous để tính YoY growth ──
    # {
    #     "section": "profitability",
    #     "kpi_name": "pbt",
    #     "kind": "money",
    #     "keywords": ["lợi nhuận trước thuế", "tổng lợi nhuận kế toán trước thuế", "profit before tax", "pbt"],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất khoản mục PBT = Profit Before Tax = Lợi nhuận trước thuế. "
    #         "Ưu tiên các dòng như 'Tổng lợi nhuận kế toán trước thuế thu nhập doanh nghiệp' hoặc "
    #         "'Lợi nhuận trước thuế' trong báo cáo kết quả kinh doanh hợp nhất. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước/cùng kỳ năm trước (previous) — "
    #         "thường là cột bên phải trong cùng bảng P&L. "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "total_operating_income",
    #     "kind": "money",
    #     "keywords": ["tổng thu nhập hoạt động", "total operating income", "toi"],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất khoản mục TOI = Total Operating Income = Tổng thu nhập hoạt động. "
    #         "Ưu tiên dòng thể hiện tổng thu nhập hoạt động của ngân hàng. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước/cùng kỳ năm trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "net_interest_income",
    #     "kind": "money",
    #     "keywords": ["thu nhập lãi thuần", "net interest income", "nii"],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất khoản mục NII = Net Interest Income = Thu nhập lãi thuần. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước/cùng kỳ năm trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "opex",
    #     "kind": "money",
    #     "keywords": [
    #         "chi phí hoạt động",
    #         "chi phi hoat dong",
    #         "operating expenses",
    #         "operating expense",
    #         "operating cost",
    #     ],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất dòng 'Chi phí hoạt động' — đây là dòng tổng chi phí hoạt động "
    #         "của toàn ngân hàng trong kỳ (thường có mã số tham chiếu như 32, 33 tuỳ ngân hàng). "
    #         "KHÔNG lấy 'Chi phí hoạt động khác' (dòng này nằm trong mục Lãi thuần từ hoạt động khác). "
    #         "KHÔNG lấy 'Chi phí từ hoạt động dịch vụ' hay bất kỳ chi phí thành phần nào. "
    #         "Chỉ lấy đúng dòng 'Chi phí hoạt động' cấp cao nhất trong P&L. "
    #         "Giá trị thường là số âm (chi phí) — lấy nguyên giá trị đó, không đổi dấu. "
    #         "Trả về giá trị kỳ hiện tại. Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # ── TOI components — dùng để tính TOI nếu không lấy trực tiếp được ────────
    # TOI = NII + net_fee_income + net_trading_income + net_securities_gain
    #           + other_operating_income + dividend_income
    # {
    #     "section": "profitability",
    #     "kpi_name": "net_fee_income",
    #     "kind": "money",
    #     "keywords": [
    #         "thu nhập thuần từ dịch vụ",
    #         "lãi thuần từ hoạt động dịch vụ",
    #         "net fee and commission income",
    #         "net fee income",
    #     ],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất dòng 'Lãi thuần từ hoạt động dịch vụ' hoặc "
    #         "'Thu nhập thuần từ dịch vụ' (Net fee and commission income). "
    #         "Đây là dòng NET (đã trừ chi phí dịch vụ) — KHÔNG lấy dòng thu nhập phí gộp "
    #         "hay dòng chi phí dịch vụ riêng lẻ. "
    #         "Giá trị có thể dương hoặc âm. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "net_trading_income",
    #     "kind": "money",
    #     "keywords": [
    #         "lãi thuần từ kinh doanh ngoại hối",
    #         "thu nhập thuần từ kinh doanh ngoại hối",
    #         "lãi thuần từ hoạt động kinh doanh ngoại hối và vàng",
    #         "net trading income",
    #         "net foreign exchange income",
    #     ],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất dòng 'Lãi thuần từ kinh doanh ngoại hối và vàng' hoặc "
    #         "'Thu nhập thuần từ kinh doanh ngoại hối' (Net trading income / Net FX income). "
    #         "Đây là dòng NET sau khi đã trừ chi phí liên quan. "
    #         "Giá trị có thể dương hoặc âm. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "net_securities_gain",
    #     "kind": "money",
    #     "keywords": [
    #         "lãi thuần từ mua bán chứng khoán",
    #         "lãi/lỗ thuần từ mua bán chứng khoán",
    #         "lãi thuần từ hoạt động mua bán chứng khoán",
    #         "net gain from securities",
    #         "net securities income",
    #     ],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất dòng 'Lãi/lỗ thuần từ mua bán chứng khoán' "
    #         "(Net gain/loss from securities trading and investment). "
    #         "Bao gồm cả chứng khoán kinh doanh (trading) và chứng khoán đầu tư (AFS/HTM) "
    #         "nếu ngân hàng gộp chung thành một dòng. "
    #         "Nếu ngân hàng tách thành 2 dòng riêng (CKKD và CKĐT) thì lấy cả 2 và ghi chú. "
    #         "Giá trị có thể dương (lãi) hoặc âm (lỗ). "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "other_operating_income",
    #     "kind": "money",
    #     "keywords": [
    #         "thu nhập hoạt động khác",
    #         "lãi thuần từ hoạt động khác",
    #         "thu nhập khác",
    #         "other operating income",
    #         "other income",
    #     ],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất dòng 'Lãi thuần từ hoạt động khác' hoặc "
    #         "'Thu nhập hoạt động khác' (Other operating income). "
    #         "Đây là dòng NET — đã trừ chi phí hoạt động khác. "
    #         "KHÔNG lấy 'Chi phí hoạt động khác' (dòng chi phí con). "
    #         "KHÔNG nhầm với dòng 'Chi phí hoạt động' tổng của toàn ngân hàng. "
    #         "Giá trị có thể dương hoặc âm. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # {
    #     "section": "profitability",
    #     "kpi_name": "dividend_income",
    #     "kind": "money",
    #     "keywords": [
    #         "thu cổ tức",
    #         "thu nhập từ góp vốn mua cổ phần",
    #         "lãi thuần từ góp vốn mua cổ phần",
    #         "dividend income",
    #     ],
    #     "request": (
    #         "Tìm đến mục 'BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT' (P&L statement). "
    #         "Trích xuất duy nhất dòng 'Thu cổ tức' hoặc "
    #         "'Lãi thuần từ góp vốn mua cổ phần' (Dividend income). "
    #         "Nếu không có dòng này thì trả về null — không bắt buộc. "
    #         "Trả về cả giá trị kỳ hiện tại (current) VÀ kỳ trước (previous). "
    #         "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
    #     ),
    # },
    # # ── CASA components — trích xuất riêng biệt, sẽ tính ratio sau ────────────
    # # CASA ratio = (a + b + c) / d
    # # a = Tiền gửi không kỳ hạn      (demand deposits / current accounts)
    # # b = Tiền gửi ký quỹ            (margin deposits / escrow)
    # # c = Tiền gửi cho mục đích riêng (earmarked / restricted deposits)
    # # d = Tổng tiền gửi khách hàng   (total customer deposits — mẫu số)
    # {
    #     "section": "other_metrics",
    #     "kpi_name": "casa_ratio_a",
    #     "kind": "money",
    #     "keywords": [
    #         "tiền gửi không kỳ hạn",
    #         "tiền vàng gửi không kỳ hạn",
    #         "tiền, vàng gửi không kỳ hạn",
    #     ],
    #     "request": (
    #         "Trích xuất dòng TỔNG tiền gửi không kỳ hạn của khách hàng (dòng cha / in đậm). "
    #         "Ví dụ BIDV hay ghi: 'Tiền, vàng gửi không kỳ hạn'. "
    #         "KHÔNG lấy các dòng con có dấu '-' như '...bằng VND' hay '...bằng vàng, ngoại tệ'. "
    #         "Trả về giá trị kỳ hiện tại (current) VÀ đầu kỳ / kỳ trước (previous) từ cùng bảng."
    #     ),
    # },
    # {
    #     "section": "other_metrics",
    #     "kpi_name": "casa_ratio_b",
    #     "kind": "money",
    #     "keywords": ["tiền gửi ký quỹ", "tiền gửi kí quỹ"],
    #     "request": (
    #         "Trích xuất dòng TỔNG tiền gửi ký quỹ (dòng cha / in đậm). "
    #         "KHÔNG lấy các dòng con có dấu '-' như '...bằng VND' hay '...bằng vàng, ngoại tệ'. "
    #         "Trả về giá trị kỳ hiện tại (current) VÀ đầu kỳ / kỳ trước (previous) từ cùng bảng. "
    #         "Nếu không có dòng này thì trả về None."
    #     ),
    # },
    # {
    #     "section": "other_metrics",
    #     "kpi_name": "casa_ratio_c",
    #     "kind": "money",
    #     "keywords": [
    #         "tiền gửi cho mục đích riêng biệt",
    #         "tiền gửi vốn chuyên dùng",
    #         "tiền gửi chuyên dùng",
    #     ],
    #     "request": (
    #         "Trích xuất dòng TỔNG tiền gửi vốn chuyên dùng hoặc tiền gửi cho mục đích "
    #         "riêng biệt (dòng cha / in đậm). "
    #         "Tên dòng có thể khác nhau theo ngân hàng: "
    #         "'tiền gửi vốn chuyên dùng' (BIDV), "
    #         "'tiền gửi cho mục đích riêng biệt' (Vietcombank/ACB...). "
    #         "KHÔNG lấy các dòng con có dấu '-' như '...bằng VND' hay '...bằng vàng, ngoại tệ'. "
    #         "Trả về giá trị kỳ hiện tại (current) VÀ đầu kỳ / kỳ trước (previous) từ cùng bảng. "
    #         "Nếu không có dòng này thì trả về None."
    #     ),
    # },
    # {
    #     "section": "other_metrics",
    #     "kpi_name": "casa_ratio_d",
    #     "kind": "money",
    #     "keywords": ["tiền gửi của khách hàng", "tổng tiền gửi khách hàng"],
    #     "request": (
    #         "Trích xuất dòng TỔNG tiền gửi của khách hàng — là dòng tổng cộng "
    #         "cuối bảng (số lớn nhất, thường không in đậm hoặc là dòng cộng cuối). "
    #         "Không lấy các dòng con (không kỳ hạn, có kỳ hạn, ký quỹ...). "
    #         "Trả về giá trị cuối kỳ hiện tại (current) VÀ đầu kỳ / kỳ trước (previous) — "
    #         "cột đầu năm (31/12/20xx) trong cùng bảng."
    #     ),
    # },
    # {
    #     "section": "lending_deposit",
    #     "kpi_name": "total_deposits",
    #     "kind": "money",
    #     "keywords": ["tiền gửi khách hàng", "huy động vốn", "total deposits", "customer deposits"],
    #     "request": (
    #         "Trích xuất duy nhất khoản mục Total Deposit = Tổng tiền gửi khách hàng / huy động vốn "
    #         "của kỳ hiện tại từ bảng cân đối kế toán hoặc phần thuyết minh tương ứng. "
    #         "Trả về cả giá trị cuối kỳ hiện tại (current) VÀ đầu kỳ / kỳ trước (previous)."
    #     ),
    # },
    {
        "section": "bctc_components",
        "kpi_name": "total_credit_reported",
        "kind": "money",
        "keywords": ["tổng dư nợ tín dụng", "tổng tín dụng", "total credit"],
        "request": (
            "Trích xuất duy nhất khoản mục 'Tổng dư nợ tín dụng' hoặc 'Tổng tín dụng' "
            "(nếu ngân hàng công bố dòng tổng này rõ ràng) từ bảng cân đối kế toán hoặc thuyết minh. "
            "Không tự cộng các thành phần — chỉ lấy nếu có dòng tổng được ghi rõ. "
            "Trả về cả giá trị cuối kỳ hiện tại (current) VÀ đầu kỳ / kỳ trước (previous). "
            "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
        ),
    },
    {
        "section": "bctc_components",
        "kpi_name": "credit_customer_loans",
        "kind": "money",
        "keywords": ["cho vay khách hàng", "dư nợ cho vay khách hàng", "loans to customers"],
        "request": (
            "Trích xuất duy nhất khoản mục 'Cho vay khách hàng' (Loans to customers) "
            "từ BẢNG CÂN ĐỐI KẾ TOÁN (phần Tài sản). "
            "Ưu tiên lấy số GỘP (Gross — trước khi trừ dự phòng). "
            "Nếu chỉ có số Net (sau dự phòng) thì lấy số Net và ghi chú rõ là Net. "
            "Trả về cả current và previous. "
            "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
        ),
    },
    {
        "section": "bctc_components",
        "kpi_name": "credit_domestic_bonds_trading",
        "kind": "money",
        "keywords": [
            "chứng khoán kinh doanh",
            "chứng khoán nợ kinh doanh",
            "trái phiếu tckt trong nước",
        ],
        "request": (
            "Tìm đến thuyết minh chi tiết của mục 'CHỨNG KHOÁN KINH DOANH' (Trading Securities). "
            "Trong phần 'Chứng khoán nợ' của rổ này, trích xuất duy nhất dòng "
            "'Trái phiếu do các tổ chức kinh tế trong nước phát hành' (Bonds issued by local economic entities). "
            "Nếu ngân hàng chỉ ghi chung 'Trái phiếu doanh nghiệp' hoặc 'Trái phiếu TCKT' thì lấy số đó và ghi chú. "
            "Nếu không có mục này trong rổ Chứng khoán kinh doanh thì trả về null. "
            "KHÔNG lấy từ rổ AFS hoặc HTM. "
            "Trả về cả current và previous. "
            "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
        ),
    },
    {
        "section": "bctc_components",
        "kpi_name": "credit_domestic_bonds_afs",
        "kind": "money",
        "keywords": [
            "chứng khoán sẵn sàng để bán",
            "afs",
            "trái phiếu tckt trong nước",
        ],
        "request": (
            "Tìm đến thuyết minh chi tiết của mục 'CHỨNG KHOÁN ĐẦU TƯ SẴN SÀNG ĐỂ BÁN' (AFS — Available for Sale). "
            "Trong phần 'Chứng khoán nợ' của rổ AFS, trích xuất duy nhất dòng "
            "'Trái phiếu do các tổ chức kinh tế trong nước phát hành' (Bonds issued by local economic entities). "
            "Nếu ngân hàng chỉ ghi chung 'Trái phiếu doanh nghiệp' hoặc 'Trái phiếu TCKT' thì lấy số đó và ghi chú. "
            "Nếu không có mục này trong rổ AFS thì trả về null. "
            "KHÔNG lấy từ rổ CKKD hoặc HTM. "
            "Trả về cả current và previous. "
            "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
        ),
    },
    {
        "section": "bctc_components",
        "kpi_name": "credit_domestic_bonds_htm",
        "kind": "money",
        "keywords": [
            "chứng khoán giữ đến ngày đáo hạn",
            "htm",
            "trái phiếu tckt trong nước",
        ],
        "request": (
            "Tìm đến thuyết minh chi tiết của mục 'CHỨNG KHOÁN ĐẦU TƯ GIỮ ĐẾN NGÀY ĐÁO HẠN' (HTM — Held to Maturity). "
            "Trong phần 'Chứng khoán nợ' của rổ HTM, trích xuất duy nhất dòng "
            "'Trái phiếu do các tổ chức kinh tế trong nước phát hành' (Bonds issued by local economic entities). "
            "Nếu ngân hàng chỉ ghi chung 'Trái phiếu doanh nghiệp' hoặc 'Trái phiếu TCKT' thì lấy số đó và ghi chú. "
            "Nếu không có mục này trong rổ HTM thì trả về null. "
            "KHÔNG lấy từ rổ CKKD hoặc AFS. "
            "Trả về cả current và previous. "
            "Ghi rõ đơn vị tính (Triệu đồng, Tỷ đồng...)."
        ),
    },
    # # ── Earning assets components (để tính/validate NIM LTM về sau) ───────────
    # {
    #     "section": "bctc_components",
    #     "kpi_name": "earning_assets_sbv_deposits",
    #     "kind": "money",
    #     "keywords": ["tiền gửi tại ngân hàng nhà nước", "tiền gửi tại nhnn"],
    #     "request": (
    #         "Trích xuất duy nhất khoản mục Tiền gửi tại Ngân hàng Nhà nước Việt Nam "
    #         "(nếu có) ở kỳ hiện tại từ bảng cân đối kế toán. Trả về cả current và previous."
    #     ),
    # },
    # {
    #     "section": "bctc_components",
    #     "kpi_name": "earning_assets_interbank_assets",
    #     "kind": "money",
    #     "keywords": ["tiền gửi tại các tctd khác", "cho vay các tctd khác"],
    #     "request": (
    #         "Trích xuất duy nhất khoản mục Tiền gửi tại các TCTD khác và cho vay các TCTD khác "
    #         "(nếu có) ở kỳ hiện tại từ bảng cân đối kế toán. Trả về cả current và previous."
    #     ),
    # },
    # {
    #     "section": "bctc_components",
    #     "kpi_name": "earning_assets_customer_loans",
    #     "kind": "money",
    #     "keywords": ["cho vay khách hàng", "loans to customers"],
    #     "request": (
    #         "Trích xuất duy nhất khoản mục Cho vay khách hàng (Loans to customers) "
    #         "để phục vụ tính tổng earning assets. Trả về cả current và previous."
    #     ),
    # },
    # {
    #     "section": "bctc_components",
    #     "kpi_name": "earning_assets_debt_securities_afs",
    #     "kind": "money",
    #     "keywords": ["chứng khoán nợ", "sẵn sàng để bán", "chứng khoán đầu tư sẵn sàng để bán"],
    #     "request": (
    #         "Trích xuất duy nhất khoản mục Chứng khoán nợ trong Chứng khoán đầu tư sẵn sàng để bán (AFS) "
    #         "(nếu có) ở kỳ hiện tại. Trả về cả current và previous."
    #     ),
    # },
    # {
    #     "section": "bctc_components",
    #     "kpi_name": "earning_assets_debt_securities_htm",
    #     "kind": "money",
    #     "keywords": ["chứng khoán nợ", "giữ đến ngày đáo hạn", "chứng khoán đầu tư giữ đến ngày đáo hạn"],
    #     "request": (
    #         "Trích xuất duy nhất khoản mục Chứng khoán nợ trong Chứng khoán đầu tư giữ đến ngày đáo hạn (HTM) "
    #         "(nếu có) ở kỳ hiện tại. Trả về cả current và previous."
    #     ),
    # },
]

KPI_REQUESTS_VERSION = "v9"  # bump when KPI_REQUESTS/prompts change (forces manifest cache refresh)


# ─────────────────────────────────────────────────────────────────────────────
#  💰  TOI FALLBACK CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def _compute_total_operating_income_from_payload(
    payload: Dict[str, Any],
    pdf_path: Path,
) -> Optional[Dict[str, Any]]:
    """
    TOI = NII + net_fee_income + net_trading_income + net_securities_gain
              + other_operating_income + dividend_income

    Chỉ dùng khi total_operating_income không trích xuất trực tiếp được.
    Đọc từ payload[section][kpi_name]["value"] / ["previous_value"] —
    khớp với schema của _build_kpi_detail.
    NII là bắt buộc; các thành phần còn lại optional (default 0).
    """
    profitability = payload.get("profitability", {}) or {}

    def _get(key: str, field: str) -> Optional[float]:
        item = profitability.get(key)
        if not isinstance(item, dict):
            return None
        return _safe_float(item.get(field))

    nii_cur  = _get("net_interest_income", "value")
    nii_prev = _get("net_interest_income", "previous_value")

    if nii_cur is None:
        logger.debug("[fs_kpi_compute] toi_computed: thiếu NII current, bỏ qua")
        return None

    def _opt(key: str, field: str) -> float:
        return _get(key, field) or 0.0

    non_ii_keys = [
        "net_fee_income",
        "net_trading_income",
        "net_securities_gain",
        "other_operating_income",
        "dividend_income",
    ]

    toi_cur  = nii_cur + sum(_opt(k, "value") for k in non_ii_keys)
    toi_prev = (
        nii_prev + sum(_opt(k, "previous_value") for k in non_ii_keys)
        if nii_prev is not None else None
    )

    # Lấy metadata từ NII item
    nii_item    = profitability.get("net_interest_income") or {}
    source_url  = nii_item.get("source_url") or f"file://{pdf_path.resolve()}"
    source_type = nii_item.get("source_type") or "financial_statement_pdf"
    unit        = nii_item.get("unit")
    period_current_label  = nii_item.get("period_current_label")
    period_previous_label = nii_item.get("period_previous_label")

    components_detail: Dict[str, Any] = {
        "nii_cur": nii_cur,
        **{f"{k}_cur": _opt(k, "value") for k in non_ii_keys},
    }
    if toi_prev is not None:
        components_detail["nii_prev"] = nii_prev
        components_detail.update(
            {f"{k}_prev": _opt(k, "previous_value") for k in non_ii_keys}
        )

    formula_cur = (
        f"TOI = NII + fee + trading + securities + other + dividend\n"
        f"    = {nii_cur:,.0f} + "
        + " + ".join(f"{_opt(k, 'value'):,.0f}" for k in non_ii_keys)
        + f" = {toi_cur:,.0f}"
    )

    return {
        "value":          round(toi_cur, 4),
        "previous_value": round(toi_prev, 4) if toi_prev is not None else None,
        "unit":           unit,
        "source_url":     source_url,
        "source_type":    source_type,
        "period_current_label":  period_current_label,
        "period_previous_label": period_previous_label,
        "source_quote":   "TOI computed from NII + Non-II components",
        "reasoning":      formula_cur,
        "components":     components_detail,
        "validation_status": "computed_from_components",
        "is_fallback_computed": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  🏦  CASA RATIO CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def _compute_casa_ratio(payload: Dict[str, Any], pdf_path: Path) -> Optional[Dict[str, Any]]:
    """
    Tính CASA ratio từ 4 thành phần đã được extract:
        CASA ratio (%) = (a + b + c) / d × 100
    """
    other = payload.get("other_metrics", {})

    def _get_val(key: str) -> Optional[float]:
        item = other.get(key)
        if not isinstance(item, dict):
            return None
        val = item.get("value")
        try:
            return float(val) if val not in (None, "", "N/A") else None
        except (TypeError, ValueError):
            return None

    val_a = _get_val("casa_ratio_a")
    val_b = _get_val("casa_ratio_b")
    val_c = _get_val("casa_ratio_c")
    val_d = _get_val("casa_ratio_d")

    missing_required: List[str] = []
    if val_a is None:
        missing_required.append("casa_ratio_a (tiền gửi không kỳ hạn)")
    if val_d is None:
        missing_required.append("casa_ratio_d (tổng tiền gửi khách hàng)")

    if missing_required:
        logger.warning(
            "[PDF] Cannot compute CASA ratio — missing required components: %s",
            ", ".join(missing_required),
        )
        return None

    if val_d == 0:
        logger.warning("[PDF] Cannot compute CASA ratio — denominator (casa_ratio_d) is zero.")
        return None

    missing_optional: List[str] = []
    if val_b is None:
        missing_optional.append("casa_ratio_b (tiền gửi ký quỹ) → used 0")
        val_b = 0.0
    if val_c is None:
        missing_optional.append("casa_ratio_c (tiền gửi mục đích riêng) → used 0")
        val_c = 0.0

    numerator  = val_a + val_b + val_c
    casa_ratio = (numerator / val_d) * 100

    formula_parts = [
        f"a (không kỳ hạn)  = {val_a:,.0f}",
        f"b (ký quỹ)         = {val_b:,.0f}",
        f"c (mục đích riêng) = {val_c:,.0f}",
        f"d (tổng tiền gửi)  = {val_d:,.0f}",
        (
            f"CASA = (a + b + c) / d × 100 "
            f"= ({val_a:,.0f} + {val_b:,.0f} + {val_c:,.0f}) / {val_d:,.0f} × 100 "
            f"= {casa_ratio:.4f}%"
        ),
    ]
    if missing_optional:
        formula_parts.append(
            "Note — optional components defaulted to 0: " + "; ".join(missing_optional)
        )

    source_url = f"file://{pdf_path.resolve()}"
    return {
        "value": round(casa_ratio, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": "financial_statement_pdf",
        "source_quote": (
            f"Computed from extracted components: "
            f"a={val_a}, b={val_b}, c={val_c}, d={val_d}"
        ),
        "reasoning": " | ".join(formula_parts),
        "components": {
            "a_demand_deposits":    val_a,
            "b_margin_deposits":    val_b,
            "c_earmarked_deposits": val_c,
            "d_total_deposits":     val_d,
            "numerator":            numerator,
        },
        "validation_status": "computed_from_components",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  📈  GROWTH CALCULATOR  (YoY hoặc YTD tuỳ context)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_growth(
    payload: Dict[str, Any],
    section: str,
    stock_kpi: str,
    growth_kpi: str,
    label: str,
    pdf_path: Path,
    growth_label: str = "YTD",
) -> Optional[Dict[str, Any]]:
    """
    Tính growth từ kpi_detail đã extract:
        growth (%) = (current / previous − 1) × 100

    growth_label: "YTD" cho balance-sheet items, "YoY" cho P&L items.
    """
    item = payload.get(section, {}).get(stock_kpi)
    if not isinstance(item, dict):
        logger.warning("[PDF] Cannot compute %s — %s not extracted.", growth_kpi, stock_kpi)
        return None

    def _to_float(v) -> Optional[float]:
        try:
            return float(v) if v not in (None, "", "N/A") else None
        except (TypeError, ValueError):
            return None

    current  = _to_float(item.get("value"))
    previous = _to_float(item.get("previous_value"))

    logger.debug(
        "[PDF] %s → stock_kpi=%s | value=%s | previous_value=%s | source_quote=%.120s",
        growth_kpi,
        stock_kpi,
        item.get("value"),
        item.get("previous_value"),
        item.get("source_quote", ""),
    )

    if current is None:
        logger.warning(
            "[PDF] Cannot compute %s — current value of %s is missing.", growth_kpi, stock_kpi
        )
        return None

    if previous is None:
        logger.warning(
            "[PDF] Cannot compute %s — previous_value of %s is None. "
            "Extractor likely did not parse the prior-period column. "
            "Check extractor schema or PDF table layout.",
            growth_kpi, stock_kpi,
        )
        return None

    if previous == 0:
        logger.warning(
            "[PDF] Cannot compute %s — previous_value of %s is 0 "
            "(likely unfilled by extractor — check _select_best_item sanitization).",
            growth_kpi, stock_kpi,
        )
        return None

    growth = (current / previous - 1) * 100

    source_url = f"file://{pdf_path.resolve()}"
    reasoning = (
        f"{label} growth ({growth_label}) = (current / previous − 1) × 100 "
        f"= ({current:,.0f} / {previous:,.0f} − 1) × 100 = {growth:.4f}%"
    )
    return {
        "value": round(growth, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": "financial_statement_pdf",
        "source_quote": (
            f"Computed from {stock_kpi}: current={current:,.0f}, previous={previous:,.0f}"
        ),
        "reasoning": reasoning,
        "components": {
            "current":  current,
            "previous": previous,
        },
        "validation_status": "computed_from_components",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  📊  CASA GROWTH CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def _compute_casa_growth_ytd(
    payload: Dict[str, Any],
    pdf_path: Path,
) -> Optional[Dict[str, Any]]:
    """
    CASA growth YTD = (sum_cur / sum_prev − 1) × 100

    sum_cur  = a_cur  + b_cur  + c_cur
    sum_prev = a_prev + b_prev + c_prev
    """
    other = payload.get("other_metrics", {}) or {}

    def _to_float(v) -> Optional[float]:
        try:
            return float(v) if v not in (None, "", "N/A") else None
        except (TypeError, ValueError):
            return None

    a_item = other.get("casa_ratio_a")
    b_item = other.get("casa_ratio_b")
    c_item = other.get("casa_ratio_c")

    if not isinstance(a_item, dict):
        logger.warning("[PDF] Cannot compute CASA growth — casa_ratio_a not extracted.")
        return None

    a_cur  = _to_float(a_item.get("value"))
    a_prev = _to_float(a_item.get("previous_value"))

    if any(v is None for v in (a_cur, a_prev)):
        logger.warning(
            "[PDF] Cannot compute CASA growth — missing required values for casa_ratio_a "
            "(current=%s, previous=%s).",
            a_cur, a_prev,
        )
        return None

    # b, c optional → default 0 nếu None
    b_cur  = _to_float((b_item or {}).get("value"))          if isinstance(b_item, dict) else None
    c_cur  = _to_float((c_item or {}).get("value"))          if isinstance(c_item, dict) else None
    b_prev = _to_float((b_item or {}).get("previous_value")) if isinstance(b_item, dict) else None
    c_prev = _to_float((c_item or {}).get("previous_value")) if isinstance(c_item, dict) else None

    b_cur  = b_cur  or 0.0
    c_cur  = c_cur  or 0.0
    b_prev = b_prev or 0.0
    c_prev = c_prev or 0.0

    sum_cur  = a_cur  + b_cur  + c_cur
    sum_prev = a_prev + b_prev + c_prev

    if sum_prev == 0:
        logger.warning("[PDF] Cannot compute CASA growth — sum_prev is 0 (division by zero).")
        return None

    growth = (sum_cur / sum_prev - 1) * 100

    source_url = f"file://{pdf_path.resolve()}"

    return {
        "value": round(growth, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": "financial_statement_pdf",
        "source_quote": (
            f"CASA growth YTD = (sum_cur / sum_prev − 1) × 100 "
            f"= ({sum_cur:,.0f} / {sum_prev:,.0f} − 1) × 100"
        ),
        "reasoning": (
            f"sum_cur  = {a_cur:,.0f} + {b_cur:,.0f} + {c_cur:,.0f} = {sum_cur:,.0f}\n"
            f"sum_prev = {a_prev:,.0f} + {b_prev:,.0f} + {c_prev:,.0f} = {sum_prev:,.0f}\n"
            f"CASA growth YTD = ({sum_cur:,.0f} / {sum_prev:,.0f} − 1) × 100 = {growth:.4f}%"
        ),
        "components": {
            "current":  sum_cur,
            "previous": sum_prev,
            "a_cur": a_cur,  "b_cur": b_cur,  "c_cur": c_cur,
            "a_prev": a_prev, "b_prev": b_prev, "c_prev": c_prev,
            "sum_cur":  round(sum_cur,  4),
            "sum_prev": round(sum_prev, 4),
        },
        "validation_status": "computed_from_components",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  📉  CIR CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def _compute_cir(payload: Dict[str, Any], pdf_path: Path) -> Optional[Dict[str, Any]]:
    """
    CIR (Cost-to-Income Ratio) = |OPEX| / TOI × 100
    - OPEX = profitability.opex (Chi phí hoạt động — thường là số âm)
    - TOI  = profitability.total_operating_income
    """
    profitability = payload.get("profitability", {}) or {}

    def _to_float(v) -> Optional[float]:
        try:
            return float(v) if v not in (None, "", "N/A") else None
        except (TypeError, ValueError):
            return None

    opex_item = profitability.get("opex")
    toi_item  = profitability.get("total_operating_income")

    if not isinstance(opex_item, dict):
        logger.warning("[PDF] Cannot compute CIR — opex not extracted.")
        return None
    if not isinstance(toi_item, dict):
        logger.warning("[PDF] Cannot compute CIR — total_operating_income not extracted.")
        return None

    opex = _to_float(opex_item.get("value"))
    toi  = _to_float(toi_item.get("value"))

    logger.debug("[PDF] cir → opex=%s, toi=%s", opex, toi)

    if opex is None:
        logger.warning("[PDF] Cannot compute CIR — opex value is None.")
        return None
    if toi is None:
        logger.warning("[PDF] Cannot compute CIR — toi value is None.")
        return None
    if toi == 0:
        logger.warning("[PDF] Cannot compute CIR — TOI is 0 (division by zero).")
        return None

    opex_abs = abs(opex)
    cir = (opex_abs / toi) * 100

    source_url = f"file://{pdf_path.resolve()}"
    return {
        "value": round(cir, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": "financial_statement_pdf",
        "source_quote": f"Computed from OPEX={opex:,.0f}, TOI={toi:,.0f}",
        "reasoning": (
            f"CIR = |OPEX| / TOI × 100 "
            f"= |{opex:,.0f}| / {toi:,.0f} × 100 = {cir:.4f}%"
        ),
        "components": {
            "opex_raw": opex,
            "opex_abs": opex_abs,
            "toi": toi,
        },
        "validation_status": "computed_from_components",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ⚙️  ENV / PATH HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_extractor_root() -> Optional[Path]:
    candidate = os.environ.get("BCTC_EXTRACTOR_ROOT", "").strip()
    if candidate:
        path = Path(candidate).expanduser()
        return path if path.exists() else None
    return DEFAULT_EXTRACTOR_ROOT if DEFAULT_EXTRACTOR_ROOT.exists() else None


def _get_pdf_dir() -> Optional[Path]:
    candidate = os.environ.get("BCTC_PDF_DIR", "").strip()
    if candidate:
        path = Path(candidate).expanduser()
        return path if path.exists() else None
    return DEFAULT_PDF_DIR if DEFAULT_PDF_DIR.exists() else None


def _ensure_manifest_parent() -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> Dict[str, Any]:
    _ensure_manifest_parent()
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_manifest(data: Dict[str, Any]) -> None:
    _ensure_manifest_parent()
    MANIFEST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pdf_signature(pdf_path: Path) -> Dict[str, Any]:
    stat = pdf_path.stat()
    return {
        "path": str(pdf_path.resolve()),
        "mtime": int(stat.st_mtime),
        "size": int(stat.st_size),
        "requests_version": KPI_REQUESTS_VERSION,
    }


def _manifest_key(config: Dict[str, Any], pdf_path: Path) -> str:
    ticker = str(config.get("ticker", "")).strip().upper()
    return f"{ticker}::{pdf_path.resolve()}"


def _get_cached_manifest_result(
    config: Dict[str, Any], pdf_path: Path
) -> Optional[Dict[str, Any]]:
    manifest = _load_manifest()
    key = _manifest_key(config, pdf_path)
    record = manifest.get(key)
    if not isinstance(record, dict):
        return None
    if record.get("signature") != _pdf_signature(pdf_path):
        return None
    logger.info("[PDF] Cache manifest hit for %s: %s", config.get("name"), pdf_path.name)
    return {
        "pdf_path": pdf_path,
        "extracted_kpis": record.get("extracted_kpis") or {},
        "fs_components": record.get("fs_components") or [],
        "article_links": record.get("article_links") or [],
    }


def _set_cached_manifest_result(
    config: Dict[str, Any],
    pdf_path: Path,
    extracted_kpis: Dict[str, Any],
    fs_components: List[Dict[str, Any]],
    article_links: List[str],
) -> None:
    manifest = _load_manifest()
    key = _manifest_key(config, pdf_path)
    manifest[key] = {
        "signature": _pdf_signature(pdf_path),
        "bank_name": config.get("name"),
        "ticker": config.get("ticker"),
        "extracted_kpis": extracted_kpis or {},
        "fs_components": fs_components or [],
        "article_links": article_links or [],
        "updated_at": str(int(Path(pdf_path).stat().st_mtime)),
    }
    _save_manifest(manifest)


# ─────────────────────────────────────────────────────────────────────────────
#  🔌  EXTRACTOR LOADER
# ─────────────────────────────────────────────────────────────────────────────

def _load_financial_extractor():
    if InternalFinancialExtractor is not None:
        return InternalFinancialExtractor

    import importlib.util

    root = _get_extractor_root()
    if not root:
        return None

    main_path = root / "extractors" / "gemini_extractor.py"
    if not main_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("bctc_gemini_extractor", main_path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "FinancialExtractor", None)


# ─────────────────────────────────────────────────────────────────────────────
#  🔍  PDF DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

def _candidate_pdf_names(config: Dict[str, Any]) -> List[str]:
    name = str(config.get("name", "")).lower()
    ticker = str(config.get("ticker", "")).lower()
    variants = {name, ticker}
    if name == "techcombank":
        variants.update({"ky_thuong", "kỹ_thương", "ky thuong"})
    if name == "vietcombank":
        variants.update({"ngoai_thuong", "ngoại_thương"})
    if name == "vietinbank":
        variants.update({"cong_thuong", "công_thương"})
    if name == "mbbank":
        variants.update({"mb", "quan_doi", "quân_đội"})
    if name == "vpbank":
        variants.update({"viet_nam_thinh_vuong", "việt_nam_thịnh_vượng"})
    if name == "bidv":
        variants.update({"dau_tu_va_phat_trien", "đầu_tư_và_phát_triển"})
    if name == "acb":
        variants.update({"a_chau", "á_châu"})
    return [v for v in variants if v]


def _tokenize_filename(file_name: str) -> List[str]:
    normalized = file_name.lower().replace(".pdf", "")
    normalized = normalized.replace("_", "-").replace(" ", "-")
    return [part for part in normalized.split("-") if part]


def find_latest_pdf_for_bank(
    config: Dict[str, Any], pdf_dir: Optional[Path] = None
) -> Optional[Path]:
    base_dir = pdf_dir or _get_pdf_dir()
    if not base_dir or not base_dir.exists():
        return None

    variants = _candidate_pdf_names(config)
    candidates: List[Path] = []
    for pdf_path in base_dir.rglob("*.pdf"):
        name_lower = pdf_path.name.lower()
        tokens = _tokenize_filename(name_lower)
        if any(
            (variant in tokens) or (len(variant) > 3 and variant in name_lower)
            for variant in variants
        ):
            candidates.append(pdf_path)

    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
#  🗂️  ITEM SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _score_item(text: str, section_title: str, keywords: List[str]) -> int:
    haystack = f"{section_title} {text}".lower()
    score = 0
    for keyword in keywords:
        if keyword.lower() in haystack:
            score += 3
    if score > 0:
        if (
            ("bằng vnd" in haystack or "bằng vnđ" in haystack or "bằng vn" in haystack or "bằng vàng" in haystack or "ngoại tệ" in haystack)
            and ("tổng" not in haystack)
        ):
            score -= 5
    return score


def _select_best_item(extraction, keywords: List[str]) -> Optional[Dict[str, Any]]:
    """
    Chọn item tốt nhất từ extraction output theo keywords.

    Fix: value_previous từ extractor thường trả về 0.0 (default của getattr)
    thay vì None khi không parse được cột đầu kỳ. Sanitize 0.0 → None tại đây
    để _compute_growth phân biệt được "thiếu dữ liệu" vs "giá trị thực sự bằng 0".
    """
    best = None
    for page in extraction.pages:
        for item in page.items:
            text = str(item.content or "").strip()
            if not text:
                continue
            score = _score_item(text, page.section_title or "", keywords)
            if score <= 0:
                continue

            current_val = getattr(item, "value_current", None)

            # ── Sanitize previous: 0.0 (extractor default) → None ────────────
            _prev_raw = getattr(item, "value_previous", None)
            previous_val = _prev_raw if _prev_raw not in (None, 0, 0.0) else None

            rank = (
                score,
                1 if previous_val not in (None, 0, 0.0) else 0,
                1 if current_val not in (None, 0, 0.0) else 0,
                abs(float(current_val or 0)),
                float(getattr(page, "confidence", 0.0) or 0.0),
            )
            candidate = {
                "page_number": page.page_number,
                "content": text,
                "current_value": current_val,
                "previous_value": previous_val,
                "period_current_label": getattr(extraction, "period_current", None),
                "period_previous_label": getattr(extraction, "period_previous", None),
                "score_rank": rank,
            }
            if not best or rank > best["score_rank"]:
                best = candidate
    return best


def _infer_unit(kind: str) -> str:
    return "%" if kind == "percent" else "million VND"


def _build_kpi_detail(pdf_path: Path, selected: Dict[str, Any], kind: str) -> Dict[str, Any]:
    source_url = f"file://{pdf_path.resolve()}#page={selected['page_number']}"
    return {
        "value": selected["current_value"],
        "unit": _infer_unit(kind),
        "source_url": source_url,
        "source_type": "financial_statement_pdf",
        "source_quote": selected["content"],
        "reasoning": "Extracted from local financial statement PDF",
        "previous_value": selected.get("previous_value"),
        "period_current_label": selected.get("period_current_label"),
        "period_previous_label": selected.get("period_previous_label"),
        "validation_status": "reported_only",
    }


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-", "N/A", "null"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _compute_total_credit_from_components(payload: Dict[str, Any], pdf_path: Path) -> Optional[Dict[str, Any]]:
    """
    Resolve Total Credit:
    - Ưu tiên dòng tổng: bctc_components.total_credit_reported
    - Fallback: cộng customer_loans + domestic_bonds_(trading/afs/htm)
    """
    comps = payload.get("bctc_components", {}) or {}
    if not isinstance(comps, dict):
        comps = {}

    def _get_item(key: str) -> Optional[Dict[str, Any]]:
        item = comps.get(key)
        return item if isinstance(item, dict) else None

    reported = _get_item("total_credit_reported")
    if reported and _safe_float(reported.get("value")) is not None:
        return {
            "value": reported.get("value"),
            "unit": reported.get("unit"),
            "source_url": reported.get("source_url") or f"file://{pdf_path.resolve()}",
            "source_type": "financial_statement_pdf",
            "source_quote": reported.get("source_quote") or "Total credit reported in financial statements",
            "reasoning": "Reported directly in financial statement (Total credit / Tổng dư nợ tín dụng).",
            "previous_value": reported.get("previous_value"),
            "period_current_label": reported.get("period_current_label"),
            "period_previous_label": reported.get("period_previous_label"),
            "validation_status": "reported_only",
        }

    parts: List[Tuple[str, str]] = [
        ("credit_customer_loans", "customer_loans"),
        ("credit_domestic_bonds_trading", "domestic_bonds_trading"),
        ("credit_domestic_bonds_afs", "domestic_bonds_afs"),
        ("credit_domestic_bonds_htm", "domestic_bonds_htm"),
    ]

    current_sum = 0.0
    previous_sum = 0.0
    any_current = False
    all_previous_present = True
    used_components: Dict[str, Any] = {}
    unit = None
    period_current_label = None
    period_previous_label = None

    for key, label in parts:
        item = _get_item(key)
        if not item:
            continue
        cur = _safe_float(item.get("value"))
        prev = _safe_float(item.get("previous_value"))
        if cur is None:
            continue
        any_current = True
        current_sum += cur
        if prev is None:
            all_previous_present = False
        else:
            previous_sum += prev
        used_components[label] = {"current": cur, "previous": prev}
        unit = unit or item.get("unit")
        period_current_label = period_current_label or item.get("period_current_label")
        period_previous_label = period_previous_label or item.get("period_previous_label")

    if not any_current:
        return None

    previous_value = previous_sum if all_previous_present else None
    reasoning = (
        "Computed Total Credit = customer_loans + domestic bonds (trading/AFS/HTM)"
        f" = {current_sum:,.0f}"
    )
    if previous_value is not None:
        reasoning += f" | previous_total_credit={previous_value:,.0f}"

    return {
        "value": round(current_sum, 4),
        "unit": unit or "million VND",
        "source_url": f"file://{pdf_path.resolve()}",
        "source_type": "financial_statement_pdf",
        "source_quote": "Computed from balance-sheet components (saved in components table).",
        "reasoning": reasoning,
        "previous_value": previous_value,
        "period_current_label": period_current_label,
        "period_previous_label": period_previous_label,
        "components": used_components,
        "validation_status": "computed_from_components",
    }


def _collect_fs_components(payload: Dict[str, Any], pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Chuẩn hoá list components để ghi vào bảng bank_fs_components.
    Bao gồm pbt, total_operating_income, net_interest_income để trace previous_value.
    """
    result: List[Dict[str, Any]] = []

    def _push(component_key: str, item: Dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        result.append(
            {
                "component_key": component_key,
                "value_current": item.get("value"),
                "value_previous": item.get("previous_value"),
                "unit": item.get("unit"),
                "period_current_label": item.get("period_current_label"),
                "period_previous_label": item.get("period_previous_label"),
                "source_url": item.get("source_url") or f"file://{pdf_path.resolve()}",
                "source_quote": item.get("source_quote"),
                "source_type": item.get("source_type") or "financial_statement_pdf",
                "reasoning": item.get("reasoning"),
            }
        )

    for section, keys in [
        (
            "profitability",
            [
                "pbt", "total_operating_income", "net_interest_income", "opex",
                "net_fee_income", "net_trading_income", "net_securities_gain",
                "other_operating_income", "dividend_income",
            ],
        ),
        ("profitability_ratios", ["nim", "cir"]),
        ("lending_deposit", ["total_deposits"]),
        ("other_metrics", ["casa_ratio_a", "casa_ratio_b", "casa_ratio_c", "casa_ratio_d", "casa_growth_ytd"]),
        (
            "bctc_components",
            [
                "total_credit_reported",
                "credit_customer_loans",
                "credit_domestic_bonds_trading",
                "credit_domestic_bonds_afs",
                "credit_domestic_bonds_htm",
                "earning_assets_sbv_deposits",
                "earning_assets_interbank_assets",
                "earning_assets_customer_loans",
                "earning_assets_debt_securities_afs",
                "earning_assets_debt_securities_htm",
            ],
        ),
    ]:
        section_map = payload.get(section) or {}
        if not isinstance(section_map, dict):
            continue
        for k in keys:
            item = section_map.get(k)
            if isinstance(item, dict):
                _push(k, item)

    return result


def _empty_extracted_payload() -> Dict[str, Dict[str, Any]]:
    return {}


# ─────────────────────────────────────────────────────────────────────────────
#  🚀  CORE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _run_pdf_extraction_sync(
    pdf_path: Path, requests: List[Dict[str, Any]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Luồng extraction đầy đủ:

    Bước 1  — Extract tất cả KPI theo KPI_REQUESTS qua FinancialExtractor (Gemini).
    Bước 1.5 — TOI fallback: nếu total_operating_income không extract được,
               tính từ NII + Non-II components.
    Bước 2  — Tính CASA ratio từ các thành phần a/b/c/d.
    Bước 2.6 — Tính CASA growth YTD.
    Bước 2.7 — Tính CIR = |OPEX| / TOI × 100.
    Bước 3  — Resolve Total Credit.
    Bước 4  — Tính Credit growth YTD.
    Bước 5  — Tính Deposit growth YTD.
    Bước 6  — Tính PBT growth YoY, TOI growth YoY, NII growth YoY.
    """
    extractor_cls = _load_financial_extractor()
    if not extractor_cls:
        raise RuntimeError("FinancialExtractor is unavailable. Check BCTC_EXTRACTOR_ROOT.")

    extractor = extractor_cls()
    payload = _empty_extracted_payload()

    # ── Bước 1: Extract tất cả KPI theo request ───────────────────────────────
    for request in requests:
        extraction = extractor.extract_report(
            pdf_path=pdf_path,
            report_type="custom",
            custom_request=request["request"],
            use_cache=False,
        )
        selected = _select_best_item(extraction, request["keywords"])
        if not selected:
            logger.debug(
                "[PDF] No match for kpi=%s in %s", request["kpi_name"], pdf_path.name
            )
            continue
        payload.setdefault(request["section"], {})
        payload[request["section"]][request["kpi_name"]] = _build_kpi_detail(
            pdf_path, selected, request["kind"]
        )

    # ── Bước 1.5: TOI fallback từ NII + Non-II components ────────────────────
    profitability = payload.get("profitability", {}) or {}
    toi_direct = profitability.get("total_operating_income")
    toi_has_value = isinstance(toi_direct, dict) and _safe_float(toi_direct.get("value")) is not None

    if not toi_has_value:
        logger.info(
            "[PDF] total_operating_income not extracted directly for %s — "
            "attempting fallback computation from NII + Non-II components.",
            pdf_path.name,
        )
        toi_computed = _compute_total_operating_income_from_payload(payload, pdf_path)
        if toi_computed is not None:
            payload.setdefault("profitability", {})
            payload["profitability"]["total_operating_income"] = toi_computed
            logger.info(
                "[PDF] ✅ TOI computed (fallback): current=%.0f, previous=%s",
                toi_computed["value"],
                str(toi_computed.get("previous_value")),
            )
        else:
            logger.warning(
                "[PDF] ⚠️  TOI could not be computed (fallback) for %s — "
                "check that NII was extracted successfully.",
                pdf_path.name,
            )
    else:
        logger.debug(
            "[PDF] total_operating_income extracted directly for %s — skipping fallback.",
            pdf_path.name,
        )

    # ── Bước 2: Tính CASA ratio ───────────────────────────────────────────────
    casa_result = _compute_casa_ratio(payload, pdf_path)
    if casa_result is not None:
        payload.setdefault("other_metrics", {})
        payload["other_metrics"]["casa_ratio"] = casa_result
        logger.info(
            "[PDF] ✅ CASA ratio computed: %.4f%% (a=%.0f, b=%.0f, c=%.0f, d=%.0f)",
            casa_result["value"],
            casa_result["components"]["a_demand_deposits"],
            casa_result["components"]["b_margin_deposits"],
            casa_result["components"]["c_earmarked_deposits"],
            casa_result["components"]["d_total_deposits"],
        )
    else:
        logger.warning("[PDF] ⚠️  CASA ratio could not be computed for %s", pdf_path.name)

    # Resolve total_deposits từ casa_ratio_d nếu chưa có
    other_metrics = payload.get("other_metrics", {}) or {}
    casa_d = other_metrics.get("casa_ratio_d")
    if isinstance(casa_d, dict) and casa_d.get("value") is not None:
        payload.setdefault("lending_deposit", {})
        if not payload["lending_deposit"].get("total_deposits"):
            payload["lending_deposit"]["total_deposits"] = {
                "value": casa_d["value"],
                "unit": casa_d.get("unit") or "million VND",
                "source_url": casa_d.get("source_url") or f"file://{pdf_path.resolve()}",
                "source_type": "financial_statement_pdf",
                "source_quote": casa_d.get("source_quote") or "Tiền gửi của khách hàng",
                "reasoning": "Resolved from casa_ratio_d (same line item: Tiền gửi của khách hàng)",
                "previous_value": casa_d.get("previous_value"),
                "period_current_label": casa_d.get("period_current_label"),
                "period_previous_label": casa_d.get("period_previous_label"),
                "validation_status": "reported_only",
            }

    # ── Bước 2.6: Tính CASA growth YTD ───────────────────────────────────────
    casa_growth = _compute_casa_growth_ytd(payload, pdf_path)
    if casa_growth is not None:
        payload.setdefault("other_metrics", {})
        payload["other_metrics"]["casa_growth_ytd"] = casa_growth
        logger.info(
            "[PDF] ✅ CASA growth (YTD) computed: %.4f%% (current=%.0f, previous=%.0f)",
            casa_growth["value"],
            casa_growth["components"]["current"],
            casa_growth["components"]["previous"],
        )
    else:
        logger.warning("[PDF] ⚠️  CASA growth could not be computed for %s", pdf_path.name)

    # ── Bước 2.7: Tính CIR ───────────────────────────────────────────────────
    cir_result = _compute_cir(payload, pdf_path)
    if cir_result is not None:
        payload.setdefault("profitability_ratios", {})
        payload["profitability_ratios"]["cir"] = cir_result
        logger.info(
            "[PDF] ✅ CIR computed: %.4f%% (opex=%.0f, toi=%.0f)",
            cir_result["value"],
            cir_result["components"]["opex_abs"],
            cir_result["components"]["toi"],
        )
    else:
        logger.warning("[PDF] ⚠️  CIR could not be computed for %s", pdf_path.name)

    # ── Bước 3: Resolve Total Credit ─────────────────────────────────────────
    total_credit = _compute_total_credit_from_components(payload, pdf_path)
    if total_credit is not None:
        payload.setdefault("lending_deposit", {})
        payload["lending_deposit"]["total_credit"] = total_credit
        logger.info(
            "[PDF] ✅ Total Credit resolved: %.0f (previous=%s)",
            _safe_float(total_credit.get("value")) or 0.0,
            str(total_credit.get("previous_value")),
        )
    else:
        logger.warning("[PDF] ⚠️  Total Credit could not be resolved for %s", pdf_path.name)

    # ── Bước 4: Tính Credit growth YTD ───────────────────────────────────────
    credit_growth = _compute_growth(
        payload, "lending_deposit", "total_credit", "credit_growth_ytd",
        "Total Credit", pdf_path, growth_label="YTD",
    )
    if credit_growth is not None:
        payload.setdefault("lending_deposit", {})
        payload["lending_deposit"]["credit_growth_ytd"] = credit_growth
        logger.info(
            "[PDF] ✅ Credit growth (YTD) computed: %.4f%% (current=%.0f, previous=%.0f)",
            credit_growth["value"],
            credit_growth["components"]["current"],
            credit_growth["components"]["previous"],
        )
    else:
        logger.warning("[PDF] ⚠️  Credit growth could not be computed for %s", pdf_path.name)

    # ── Bước 5: Tính Deposit growth YTD ──────────────────────────────────────
    deposit_growth = _compute_growth(
        payload, "lending_deposit", "total_deposits", "deposit_growth_ytd",
        "Total Deposits", pdf_path, growth_label="YTD",
    )
    if deposit_growth is not None:
        payload.setdefault("lending_deposit", {})
        payload["lending_deposit"]["deposit_growth_ytd"] = deposit_growth
        logger.info(
            "[PDF] ✅ Deposit growth (YTD) computed: %.4f%% (current=%.0f, previous=%.0f)",
            deposit_growth["value"],
            deposit_growth["components"]["current"],
            deposit_growth["components"]["previous"],
        )
    else:
        logger.warning("[PDF] ⚠️  Deposit growth could not be computed for %s", pdf_path.name)

    # ── Bước 6: Tính PBT / TOI / NII growth YoY ─────────────────────────────
    # growth (%) = (kỳ này / cùng kỳ năm trước − 1) × 100
    # previous_value = cột "Cùng kỳ năm trước" trong P&L (đã extract ở Bước 1).
    _pl_growth_specs = [
        ("profitability", "pbt",                   "pbt_growth", "PBT"),
        ("profitability", "total_operating_income", "toi_growth", "TOI"),
        ("profitability", "net_interest_income",    "nii_growth", "NII"),
    ]
    for _section, _stock_kpi, _growth_kpi, _label in _pl_growth_specs:
        growth_result = _compute_growth(
            payload, _section, _stock_kpi, _growth_kpi,
            _label, pdf_path, growth_label="YoY",
        )
        if growth_result is not None:
            payload.setdefault(_section, {})
            payload[_section][_growth_kpi] = growth_result
            logger.info(
                "[PDF] ✅ %s growth (YoY) computed: %.4f%% (current=%.0f, previous=%.0f)",
                _label,
                growth_result["value"],
                growth_result["components"]["current"],
                growth_result["components"]["previous"],
            )
        else:
            logger.warning(
                "[PDF] ⚠️  %s growth (YoY) could not be computed for %s — "
                "check that extractor returned previous_value (cùng kỳ năm trước) for %s.",
                _label, pdf_path.name, _stock_kpi,
            )

    fs_components = _collect_fs_components(payload, pdf_path)
    return payload, fs_components


# ─────────────────────────────────────────────────────────────────────────────
#  🔄  ASYNC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def extract_pdf_kpis_for_bank(config: Dict[str, Any]) -> Dict[str, Any]:
    pdf_path = None
    try:
        pdf_path = find_latest_pdf_for_bank(config)
        if not pdf_path:
            return {
                "pdf_path": None,
                "extracted_kpis": {},
                "fs_components": [],
                "article_links": [],
                "skip_reason": "no_pdf_found",
            }

        manifest_result = _get_cached_manifest_result(config, pdf_path)
        if manifest_result is not None:
            if not (manifest_result.get("fs_components") or []):
                manifest_result["skip_reason"] = "manifest_cache_empty"
            return manifest_result

        logger.info("[PDF] Found BCTC for %s: %s", config.get("name"), pdf_path.name)
        loop = asyncio.get_running_loop()
        extracted_kpis = await loop.run_in_executor(
            None, _run_pdf_extraction_sync, pdf_path, KPI_REQUESTS
        )
        if isinstance(extracted_kpis, tuple) and len(extracted_kpis) == 2:
            extracted_kpis, fs_components = extracted_kpis
        else:
            fs_components = []

        # Chỉ giữ các KPI final để merge vào snapshot;
        # raw components được lưu riêng (bank_fs_components).
        snapshot_kpis = copy.deepcopy(extracted_kpis or {})
        if isinstance(snapshot_kpis, dict):
            snapshot_kpis.pop("bctc_components", None)
            # Giữ đúng các KPI final trong other_metrics
            other = snapshot_kpis.get("other_metrics")
            if isinstance(other, dict):
                kept_other = {}
                for key in ("casa_ratio", "casa_growth_ytd"):
                    if other.get(key) is not None:
                        kept_other[key] = other[key]
                snapshot_kpis["other_metrics"] = kept_other
            # Giữ đúng các KPI final trong profitability (bỏ Non-II components thô)
            profitability_snap = snapshot_kpis.get("profitability")
            if isinstance(profitability_snap, dict):
                _non_ii_component_keys = {
                    "net_fee_income", "net_trading_income", "net_securities_gain",
                    "other_operating_income", "dividend_income",
                }
                kept_profitability = {
                    k: v for k, v in profitability_snap.items()
                    if k not in _non_ii_component_keys
                }
                snapshot_kpis["profitability"] = kept_profitability

        source_url = f"file://{pdf_path.resolve()}"
        result = {
            "pdf_path": pdf_path,
            "extracted_kpis": snapshot_kpis or {},
            "fs_components": fs_components or [],
            "article_links": [source_url] if extracted_kpis else [],
            "skip_reason": None,
        }
        if not result["fs_components"]:
            logger.warning(
                "[PDF] Extracted 0 fs_components for %s (%s). "
                "Likely causes: extractor returned no items, keywords mismatch, or PDF is scanned/non-searchable.",
                config.get("name"),
                pdf_path.name,
            )
            result["skip_reason"] = "extracted_empty"
        _set_cached_manifest_result(
            config, pdf_path, result["extracted_kpis"], result["fs_components"], result["article_links"]
        )
        return result
    except Exception as exc:
        logger.warning(
            "[PDF] Skip BCTC ingestion for %s due to error: %s", config.get("name"), exc
        )
        return {
            "pdf_path": pdf_path,
            "extracted_kpis": {},
            "fs_components": [],
            "article_links": [],
            "skip_reason": "exception",
        }


# ─────────────────────────────────────────────────────────────────────────────
#  🔀  MERGE HELPER
# ─────────────────────────────────────────────────────────────────────────────

def merge_extracted_kpis_with_pdf_priority(
    web_kpis: Dict[str, Any], pdf_kpis: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Merge rule: web data điền trước, PDF overwrite sau.
    PDF được ưu tiên vì là nguồn kiểm toán chính xác hơn web scraping.
    """
    merged = copy.deepcopy(web_kpis or {})
    for section, kpis in (pdf_kpis or {}).items():
        if not isinstance(kpis, dict):
            continue
        merged.setdefault(section, {})
        for kpi_name, details in kpis.items():
            merged[section][kpi_name] = details
    return merged