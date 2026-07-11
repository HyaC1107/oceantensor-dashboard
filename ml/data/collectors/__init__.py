# ML-standalone collectors (DB 의존 없음, DataFrame 반환)
from .nifs_ml import fetch_nifs_df
from .kma_ml import fetch_kma_df
from .koem_ml import fetch_koem_df
from .kwater_ml import fetch_kwater_df
from .cmems_ml import fetch_cmems_df

__all__ = ["fetch_nifs_df", "fetch_kma_df", "fetch_koem_df", "fetch_kwater_df", "fetch_cmems_df"]
