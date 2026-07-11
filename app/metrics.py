from prometheus_client import Gauge

water_temp_gauge = Gauge("water_temp", "Water Temperature (℃)", ["farm_id"])
wbi_score_gauge = Gauge("wbi_score", "WBI Score (황백화 지수)", ["farm_id"])
do_gauge = Gauge("dissolved_oxygen", "Dissolved Oxygen (mg/L)", ["farm_id"])
din_gauge = Gauge("din", "Dissolved Inorganic Nitrogen (μmol/L)", ["farm_id"])
dip_gauge = Gauge("dip", "Dissolved Inorganic Phosphorus (μmol/L)", ["farm_id"])
salinity_gauge = Gauge("salinity", "Salinity (PSU)", ["farm_id"])
np_ratio_gauge = Gauge("np_ratio", "N:P Ratio", ["farm_id"])


def update_sensor_metrics(data: dict) -> None:
    farm_id = data.get("farm_id", "A7")
    if (v := data.get("water_temp")) is not None:
        water_temp_gauge.labels(farm_id=farm_id).set(v)
    if (v := data.get("wbi_score")) is not None:
        wbi_score_gauge.labels(farm_id=farm_id).set(v)
    if (v := data.get("dissolved_oxygen")) is not None:
        do_gauge.labels(farm_id=farm_id).set(v)
    if (v := data.get("din")) is not None:
        din_gauge.labels(farm_id=farm_id).set(v)
    if (v := data.get("dip")) is not None:
        dip_gauge.labels(farm_id=farm_id).set(v)
    if (v := data.get("salinity")) is not None:
        salinity_gauge.labels(farm_id=farm_id).set(v)
    if (v := data.get("np_ratio")) is not None:
        np_ratio_gauge.labels(farm_id=farm_id).set(v)
