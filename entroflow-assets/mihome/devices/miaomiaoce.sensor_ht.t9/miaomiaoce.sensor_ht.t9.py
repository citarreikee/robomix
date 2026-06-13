# -*- coding: utf-8 -*-
"""
Miaomiaoce Temperature Humidity Sensor — 米家智能温湿度计3.
"""
DEVICE_INFO = {
    "model": "miaomiaoce.sensor_ht.t9",
    "display_name": "米家智能温湿度计3 (miaomiaoce.sensor_ht.t9)",
    "manufacturer": "miaomiaoce",
    "category": "temperature-humidity-sensor",
    "platform": "mihome",
}

SUPPORTED_ACTIONS = []

ACTION_SPECS = []

STATUS_FIELDS = [
    {
        "field": "battery",
        "description": "Battery level.",
        "type": "number"
    },
    {
        "field": "temperature",
        "description": "Temperature.",
        "type": "number"
    },
    {
        "field": "humidity",
        "description": "Humidity %.",
        "type": "number"
    }
]

MIOT_MAPPING = {
    "battery": {
        "siid": 2,
        "piid": 1003
    },
    "temperature": {
        "siid": 3,
        "piid": 1001
    },
    "humidity": {
        "siid": 3,
        "piid": 1002
    }
}

ACTION_MAPPING = {}

class DeviceClass:
    """Miaomiaoce Temperature Humidity Sensor T9 device controller."""

    def __init__(self, did: str, connector, record=None):
        self.did = did
        self.client = connector
        self.record = record or {}

    def _set_prop(self, key, value):
        m = MIOT_MAPPING.get(key)
        if not m:
            return f"Error: unknown property '{key}'."
        try:
            self.client.set_miot_property(self.did, m["siid"], m["piid"], value)
            return f"{key} = {value} (ok)"
        except Exception as e:
            return f"{key} failed: {e}"

    def _get_prop(self, key):
        m = MIOT_MAPPING.get(key)
        if not m:
            return f"Error: unknown property '{key}'."
        try:
            if hasattr(self.client, "get_miot_property"):
                return self.client.get_miot_property(self.did, m["siid"], m["piid"])
            result = self.client.get_miot_properties(self.did, [m])
            return self._extract_value(result, key)
        except Exception as e:
            return f"{key} failed: {e}"

    def _get_props(self):
        props = [dict(mapping, key=key) for key, mapping in MIOT_MAPPING.items()]
        result = self.client.get_miot_properties(self.did, props)
        return {item["key"]: self._extract_value(result, item["key"], index) for index, item in enumerate(props)}

    def _extract_value(self, result, key, index=0):
        if isinstance(result, dict):
            result = result.get("result", result.get("params", result))
        if isinstance(result, list):
            if index >= len(result):
                return None
            item = result[index]
            if isinstance(item, dict):
                if item.get("code") not in (None, 0):
                    return f"Error code {item.get('code')}"
                return item.get("value")
            return item
        if isinstance(result, dict):
            if key in result:
                return result.get(key)
            if "value" in result:
                return result.get("value")
        return result

    def query_status(self):
        try:
            values = self._get_props()
        except Exception as e:
            return f"status query failed: {e}"
        return "\n".join([
            f"battery: {values.get('battery')}",
            f"temperature: {values.get('temperature')}",
            f"humidity: {values.get('humidity')}",
        ])

    def _run_action(self, action_key):
        m = ACTION_MAPPING.get(action_key)
        if not m:
            return f"Error: unknown action '{action_key}'."
        try:
            self.client.action(self.did, m["siid"], m["aiid"], [])
            return f"{action_key} ok"
        except Exception as e:
            return f"{action_key} failed: {e}"


    def get_battery(self):
        """Battery level."""
        return self._get_prop("battery")
    def get_temperature(self):
        """Temperature."""
        return self._get_prop("temperature")
    def get_humidity(self):
        """Relative humidity %."""
        return self._get_prop("humidity")


MiaomiaoceSensorHtT9 = DeviceClass
