"""
peer_pools.py
=============
Hand-curated candidate ticker pools for the OPCM peer cascade.

Each pool maps an internal sector bucket (see `sector_mapping.py`) to a list
of yfinance-compatible tickers. Tickers are tagged with a 2-letter ISO
country code so the geography filter (Tier 1) can run without an extra
yfinance round-trip.

Design notes
------------
- Minimum ~30 names per bucket where regional coverage allows.
- Pools are intentionally biased toward ASEAN (Tier A) + broader Asia EM
  (Tier B). Selected GCC / LatAm names included as fallback (Tier C).
- We do NOT auto-generate pools. Pool composition is the single most
  consequential analyst judgment; auto-generation is the highest-risk place
  for AI hallucination.
- Tickers as of 2025-Q1; verify quarterly. yfinance occasionally renames
  suffixes (e.g., ".SI" vs no suffix); broken tickers will be reported in
  the diagnostic panel.
"""

from __future__ import annotations
from typing import Dict, List, Tuple

# (yfinance_ticker, ISO2 country code, short label)
PEER_POOLS: Dict[str, List[Tuple[str, str, str]]] = {
    # ------------------------------------------------------------------
    "banks": [
        # Thailand
        ("BBL.BK",  "TH", "Bangkok Bank"),
        ("KBANK.BK","TH", "Kasikornbank"),
        ("SCB.BK",  "TH", "SCB X"),
        ("KTB.BK",  "TH", "Krung Thai Bank"),
        ("TTB.BK",  "TH", "TMBThanachart"),
        # Indonesia
        ("BBCA.JK", "ID", "Bank Central Asia"),
        ("BBRI.JK", "ID", "Bank Rakyat Indonesia"),
        ("BMRI.JK", "ID", "Bank Mandiri"),
        ("BBNI.JK", "ID", "Bank Negara Indonesia"),
        # Malaysia
        ("1155.KL", "MY", "Maybank"),
        ("1023.KL", "MY", "CIMB Group"),
        ("5819.KL", "MY", "Hong Leong Bank"),
        ("1295.KL", "MY", "Public Bank"),
        # Philippines
        ("BDO.PS",  "PH", "BDO Unibank"),
        ("BPI.PS",  "PH", "Bank of the Philippine Islands"),
        ("MBT.PS",  "PH", "Metropolitan Bank"),
        # Singapore
        ("D05.SI",  "SG", "DBS Group"),
        ("O39.SI",  "SG", "OCBC"),
        ("U11.SI",  "SG", "UOB"),
        # India
        ("HDFCBANK.NS", "IN", "HDFC Bank"),
        ("ICICIBANK.NS","IN", "ICICI Bank"),
        ("KOTAKBANK.NS","IN", "Kotak Mahindra Bank"),
        ("AXISBANK.NS", "IN", "Axis Bank"),
        ("SBIN.NS",     "IN", "State Bank of India"),
        # China / HK
        ("1398.HK", "HK", "ICBC"),
        ("3988.HK", "HK", "Bank of China"),
        ("0939.HK", "HK", "China Construction Bank"),
        ("3328.HK", "HK", "Bank of Communications"),
        # Taiwan
        ("2882.TW", "TW", "Cathay Financial"),
        ("2891.TW", "TW", "CTBC Financial"),
        # Korea
        ("105560.KS","KR", "KB Financial"),
        ("055550.KS","KR", "Shinhan Financial"),
        # GCC (Tier C fallback)
        ("EMIRATESNBD.AE","AE","Emirates NBD"),
        ("ALRAJHI.SR","SA","Al Rajhi Bank"),
    ],
    # ------------------------------------------------------------------
    "insurance": [
        ("AIA.HK",   "HK", "AIA Group"),
        ("2318.HK",  "HK", "Ping An Insurance"),
        ("2628.HK",  "HK", "China Life"),
        ("2601.HK",  "HK", "China Pacific Insurance"),
        ("BLA.BK",   "TH", "Bangkok Life Assurance"),
        ("TLI.BK",   "TH", "Thai Life Insurance"),
        ("AMAR.JK",  "ID", "Asuransi Multi Artha Guna"),
        ("ALLIANZ.JK","ID","Allianz Life Indonesia"),
        ("PNB.PS",   "PH", "Philippine National Bank"),
        ("LIC.NS",   "IN", "Life Insurance Corporation"),
        ("SBILIFE.NS","IN","SBI Life Insurance"),
        ("HDFCLIFE.NS","IN","HDFC Life"),
        ("ICICIPRULI.NS","IN","ICICI Prudential Life"),
        ("MAXFIN.NS","IN","Max Financial Services"),
        ("2328.HK",  "HK", "PICC Property"),
        ("000060.KS","KR","Meritz Insurance"),
        ("032830.KS","KR","Samsung Life"),
    ],
    # ------------------------------------------------------------------
    "financials_brokerage": [
        ("ASIASEC.BK","TH","Asia Securities"),
        ("ASP.BK",    "TH","Asia Plus"),
        ("MAYBANK-SEC.KL","MY","Maybank Securities"),
        ("PSEC.PS",   "PH","Philippine Equity Partners"),
        ("AHL.JK",    "ID","Adhi Sarana Nusantara"),
        ("MIRAE.KS",  "KR","Mirae Asset Securities"),  # 006800
        ("006800.KS", "KR","Mirae Asset Securities"),
        ("016360.KS", "KR","Samsung Securities"),
        ("NUVOCO.NS", "IN","Nuvama Wealth"),
        ("MOTILALOFS.NS","IN","Motilal Oswal"),
        ("ANGELONE.NS","IN","Angel One"),
        ("IIFL.NS",   "IN","IIFL Securities"),
        ("CITICSEC.HK","HK","CITIC Securities"),  # alias 6030.HK
        ("6030.HK",   "HK","CITIC Securities"),
        ("6837.HK",   "HK","Haitong Securities"),
        ("3958.HK",   "HK","Dongxing Securities"),
        ("KGI.TW",    "TW","KGI Securities"),
        ("2880.TW",   "TW","Hua Nan Financial"),
        ("UOB-KH.SI", "SG","UOB Kay Hian"),
    ],
    # ------------------------------------------------------------------
    "real_estate_developer": [
        ("LH.BK",     "TH","Land & Houses"),
        ("AP.BK",     "TH","AP Thailand"),
        ("SIRI.BK",   "TH","Sansiri"),
        ("PSH.BK",    "TH","Pruksa Holding"),
        ("CPN.BK",    "TH","Central Pattana"),
        ("BSDE.JK",   "ID","Bumi Serpong Damai"),
        ("LPKR.JK",   "ID","Lippo Karawaci"),
        ("CTRA.JK",   "ID","Ciputra Development"),
        ("PWON.JK",   "ID","Pakuwon Jati"),
        ("SMRA.JK",   "ID","Summarecon Agung"),
        ("SPSETIA.KL","MY","SP Setia"),
        ("IOIPG.KL",  "MY","IOI Properties"),
        ("SUNWAY.KL", "MY","Sunway Berhad"),
        ("ALI.PS",    "PH","Ayala Land"),
        ("SMPH.PS",   "PH","SM Prime Holdings"),
        ("MEG.PS",    "PH","Megaworld"),
        ("CITY.SI",   "SG","City Developments"),
        ("DBSDIAM.SI","SG","UOL Group"),
        ("DLF.NS",    "IN","DLF Limited"),
        ("GODREJPROP.NS","IN","Godrej Properties"),
        ("OBEROIRLTY.NS","IN","Oberoi Realty"),
        ("PHOENIXLTD.NS","IN","Phoenix Mills"),
        ("PRESTIGE.NS","IN","Prestige Estates"),
        ("0688.HK",   "HK","China Overseas Land"),
        ("1109.HK",   "HK","China Resources Land"),
        ("0960.HK",   "HK","Longfor Group"),
        ("3900.HK",   "HK","Greentown China"),
        ("2007.HK",   "HK","Country Garden"),
        ("000002.SZ", "CN","China Vanke"),
    ],
    # ------------------------------------------------------------------
    "consumer_retail": [
        ("CPALL.BK",   "TH","CP All"),
        ("BJC.BK",     "TH","Berli Jucker"),
        ("HMPRO.BK",   "TH","Home Product Center"),
        ("GLOBAL.BK",  "TH","Siam Global House"),
        ("ACES.JK",    "ID","Ace Hardware Indonesia"),
        ("MAPI.JK",    "ID","Mitra Adiperkasa"),
        ("RALS.JK",    "ID","Ramayana Lestari"),
        ("AEON.KL",    "MY","AEON Co Malaysia"),
        ("PCHEM.KL",   "MY","99 Speed Mart"),
        ("ROBINS.PS",  "PH","Robinsons Retail"),
        ("PGOLD.PS",   "PH","Puregold Price Club"),
        ("DFI.SI",     "SG","DFI Retail Group"),
        ("DMART.NS",   "IN","Avenue Supermarts"),
        ("TRENT.NS",   "IN","Trent"),
        ("ABFRL.NS",   "IN","Aditya Birla Fashion"),
        ("VMART.NS",   "IN","V-Mart Retail"),
        ("SHOPERSTOP.NS","IN","Shoppers Stop"),
        ("6862.HK",    "HK","Haidilao"),
        ("1929.HK",    "HK","Chow Tai Fook"),
        ("2331.HK",    "HK","Li Ning"),
    ],
    # ------------------------------------------------------------------
    "consumer_staples": [
        ("CPF.BK",     "TH","Charoen Pokphand Foods"),
        ("OSP.BK",     "TH","Osotspa"),
        ("CBG.BK",     "TH","Carabao Group"),
        ("M.BK",       "TH","MK Restaurant"),
        ("INDF.JK",    "ID","Indofood Sukses Makmur"),
        ("ICBP.JK",    "ID","Indofood CBP"),
        ("MYOR.JK",    "ID","Mayora Indah"),
        ("UNVR.JK",    "ID","Unilever Indonesia"),
        ("HMSP.JK",    "ID","HM Sampoerna"),
        ("GGRM.JK",    "ID","Gudang Garam"),
        ("NESTLE.KL",  "MY","Nestle Malaysia"),
        ("F&N.KL",     "MY","Fraser & Neave"),
        ("URC.PS",     "PH","Universal Robina"),
        ("JFC.PS",     "PH","Jollibee Foods"),
        ("WLCON.PS",   "PH","Wilcon Depot"),
        ("THBEV.SI",   "SG","ThaiBev"),
        ("NESTLEIND.NS","IN","Nestle India"),
        ("HINDUNILVR.NS","IN","Hindustan Unilever"),
        ("ITC.NS",      "IN","ITC Limited"),
        ("BRITANNIA.NS","IN","Britannia Industries"),
        ("DABUR.NS",    "IN","Dabur India"),
        ("0291.HK",     "HK","China Resources Beer"),
        ("0322.HK",     "HK","Tingyi Holdings"),
        ("2319.HK",     "HK","Mengniu Dairy"),
        ("0151.HK",     "HK","Want Want China"),
        ("000858.SZ",   "CN","Wuliangye Yibin"),
        ("600519.SS",   "CN","Kweichow Moutai"),
    ],
    # ------------------------------------------------------------------
    "materials": [
        ("SCC.BK",     "TH","Siam Cement"),
        ("SCGP.BK",    "TH","SCG Packaging"),
        ("PTTGC.BK",   "TH","PTT Global Chemical"),
        ("IVL.BK",     "TH","Indorama Ventures"),
        ("INTP.JK",    "ID","Indocement"),
        ("SMGR.JK",    "ID","Semen Indonesia"),
        ("KRAS.JK",    "ID","Krakatau Steel"),
        ("INKP.JK",    "ID","Indah Kiat Pulp & Paper"),
        ("PETRONM.KL", "MY","Petron Malaysia"),
        ("PCHEM.KL",   "MY","Petronas Chemicals"),
        ("HEXAGON.PS", "PH","Holcim Philippines"),
        ("TATASTEEL.NS","IN","Tata Steel"),
        ("JSWSTEEL.NS","IN","JSW Steel"),
        ("HINDALCO.NS","IN","Hindalco"),
        ("ULTRACEMCO.NS","IN","UltraTech Cement"),
        ("SHREECEM.NS","IN","Shree Cement"),
        ("VEDL.NS",    "IN","Vedanta"),
        ("0914.HK",    "HK","Anhui Conch Cement"),
        ("0323.HK",    "HK","Maanshan Iron & Steel"),
        ("2600.HK",    "HK","Aluminum Corp of China"),
        ("3323.HK",    "HK","CNBM"),
        ("2002.TW",    "TW","China Steel"),
    ],
    # ------------------------------------------------------------------
    "energy_oil_gas": [
        ("PTT.BK",     "TH","PTT PCL"),
        ("PTTEP.BK",   "TH","PTT E&P"),
        ("BCP.BK",     "TH","Bangchak"),
        ("TOP.BK",     "TH","Thai Oil"),
        ("PGAS.JK",    "ID","Perusahaan Gas Negara"),
        ("MEDC.JK",    "ID","Medco Energi"),
        ("ADRO.JK",    "ID","Adaro Energy"),
        ("ITMG.JK",    "ID","Indo Tambangraya Megah"),
        ("PETD.KL",    "MY","Petronas Dagangan"),
        ("DIALOG.KL",  "MY","Dialog Group"),
        ("PCOR.PS",    "PH","Petron Philippines"),
        ("ONGC.NS",    "IN","ONGC"),
        ("RELIANCE.NS","IN","Reliance Industries"),
        ("IOC.NS",     "IN","Indian Oil"),
        ("BPCL.NS",    "IN","BPCL"),
        ("HINDPETRO.NS","IN","HPCL"),
        ("GAIL.NS",    "IN","GAIL India"),
        ("0883.HK",    "HK","CNOOC"),
        ("0857.HK",    "HK","PetroChina"),
        ("0386.HK",    "HK","Sinopec"),
        ("ARAMCO.SR",  "SA","Saudi Aramco"),
    ],
    # ------------------------------------------------------------------
    "tech_software": [
        ("DELTA.BK",   "TH","Delta Electronics Thailand"),
        ("HANA.BK",    "TH","Hana Microelectronics"),
        ("KCE.BK",     "TH","KCE Electronics"),
        ("INET.JK",    "ID","Indointernet"),
        ("MTDL.JK",    "ID","Metrodata Electronics"),
        ("GHL.KL",     "MY","GHL Systems"),
        ("MYEG.KL",    "MY","MY EG Services"),
        ("VITRO.PS",   "PH","Vitro"),
        ("VEN.SI",     "SG","Venture Corporation"),
        ("INFY.NS",    "IN","Infosys"),
        ("TCS.NS",     "IN","Tata Consultancy Services"),
        ("WIPRO.NS",   "IN","Wipro"),
        ("HCLTECH.NS", "IN","HCL Technologies"),
        ("TECHM.NS",   "IN","Tech Mahindra"),
        ("LTIM.NS",    "IN","LTIMindtree"),
        ("MPHASIS.NS", "IN","Mphasis"),
        ("PERSISTENT.NS","IN","Persistent Systems"),
        ("COFORGE.NS", "IN","Coforge"),
        ("0700.HK",    "HK","Tencent"),
        ("9988.HK",    "HK","Alibaba"),
        ("3690.HK",    "HK","Meituan"),
        ("9618.HK",    "HK","JD.com"),
        ("2330.TW",    "TW","TSMC"),
        ("2454.TW",    "TW","MediaTek"),
        ("035420.KS",  "KR","NAVER"),
        ("035720.KS",  "KR","Kakao"),
    ],
    # ------------------------------------------------------------------
    "aviation_transport": [
        ("AAV.BK",     "TH","Asia Aviation"),
        ("AOT.BK",     "TH","Airports of Thailand"),
        ("BA.BK",      "TH","Bangkok Airways"),
        ("THAI.BK",    "TH","Thai Airways"),
        ("GIAA.JK",    "ID","Garuda Indonesia"),
        ("AIRASIA.KL", "MY","AirAsia X"),
        ("CEB.PS",     "PH","Cebu Pacific"),
        ("SIAEC.SI",   "SG","SIA Engineering"),
        ("C6L.SI",     "SG","Singapore Airlines"),
        ("INDIGO.NS",  "IN","InterGlobe Aviation"),
        ("SPICEJET.NS","IN","SpiceJet"),
        ("0293.HK",    "HK","Cathay Pacific"),
        ("0753.HK",    "HK","Air China"),
        ("0670.HK",    "HK","China Eastern Airlines"),
        ("1055.HK",    "HK","China Southern Airlines"),
        ("003490.KS",  "KR","Korean Air"),
        ("020560.KS",  "KR","Asiana Airlines"),
    ],
    # ------------------------------------------------------------------
    "industrials": [
        ("WHA.BK",     "TH","WHA Corporation"),
        ("AMATA.BK",   "TH","Amata Corporation"),
        ("ROJNA.BK",   "TH","Rojana Industrial Park"),
        ("STECON.BK",  "TH","Sino-Thai Engineering"),
        ("KIJA.JK",    "ID","Kawasan Industri Jababeka"),
        ("SSIA.JK",    "ID","Surya Semesta Internusa"),
        ("DEIM.JK",    "ID","Modern Industrial"),
        ("SIME.KL",    "MY","Sime Darby"),
        ("YTL.KL",     "MY","YTL Corporation"),
        ("AC.PS",      "PH","Ayala Corporation"),
        ("DMC.PS",     "PH","DMCI Holdings"),
        ("KEP.SI",     "SG","Keppel Corporation"),
        ("BN4.SI",     "SG","Keppel Corporation alt"),
        ("LT.NS",      "IN","Larsen & Toubro"),
        ("SIEMENS.NS", "IN","Siemens India"),
        ("ABB.NS",     "IN","ABB India"),
        ("THERMAX.NS", "IN","Thermax"),
        ("CUMMINSIND.NS","IN","Cummins India"),
        ("0144.HK",    "HK","China Merchants Port"),
        ("1816.HK",    "HK","CGN Power"),
        ("3308.HK",    "HK","Golden Eagle Retail"),
    ],
}


def get_pool(bucket: str) -> List[Tuple[str, str, str]]:
    """Return the candidate pool for a sector bucket; empty list if unknown."""
    return list(PEER_POOLS.get(bucket, []))
