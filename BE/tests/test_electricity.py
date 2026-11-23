import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Response
from app.main import app
from app.api.routes.electricity import DemandResponse, get_demand
from app.services.electricity import DEFAULT_DATA_PATH, load_demand


class ElectricityTests(unittest.TestCase):
    def dataset(self, values):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "demand.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["iso3", "month", "metric", "fuel", "value", "unit"])
            writer.writerows(values)
        return path

    def test_processed_dataset_matches_raw_source(self):
        processed = load_demand(DEFAULT_DATA_PATH)
        raw = load_demand(DEFAULT_DATA_PATH.parents[1] / "raw" / "ember-monthly-generation.csv")
        self.assertEqual(processed["records"], raw["records"])
        self.assertGreater(processed["total"], 0)

    def test_sorting_filtering_and_zero_values(self):
        path = self.dataset([["VNM", "2025-02", "demand", "", 2, "TWh"],
                             ["ARG", "2025-01", "demand", "", 99, "TWh"],
                             ["VNM", "2025-01", "demand", "", 0, "TWh"]])
        data = load_demand(path)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["records"][0], {"month": "2025-01", "value": 0})

    def test_rejects_duplicates_bad_units_and_nonfinite_values(self):
        for rows in [
            [["VNM", "2025-01", "demand", "", 1, "TWh"]] * 2,
            [["VNM", "2025-13", "demand", "", 1, "TWh"]],
            [["VNM", "2025-01", "demand", "", "NaN", "TWh"]],
            [["VNM", "2025-01", "demand", "", -1, "TWh"]],
            [["VNM", "2025-01", "demand", "", 1, "MW"]],
        ]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                load_demand(self.dataset(rows))

    def test_route_contract_headers_and_cors_configuration(self):
        response = Response()
        with patch.dict(os.environ, {"ELECTRICITY_DATA_PATH": str(DEFAULT_DATA_PATH)}):
            data = DemandResponse.model_validate(get_demand(response)).model_dump()
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(data["records"], load_demand(DEFAULT_DATA_PATH)["records"])
        self.assertEqual(data["total"], len(data["records"]))
        self.assertIn("/api/electricity/demand", app.openapi()["paths"])
        cors = next(middleware for middleware in app.user_middleware if middleware.cls.__name__ == "CORSMiddleware")
        self.assertIn("http://localhost:3000", cors.kwargs["allow_origins"])
        self.assertIn("http://127.0.0.1:3000", cors.kwargs["allow_origins"])

    def test_missing_dataset_returns_503(self):
        with patch.dict(os.environ, {"ELECTRICITY_DATA_PATH": str(DEFAULT_DATA_PATH.with_name("missing.csv"))}):
            with self.assertRaises(HTTPException) as error:
                get_demand(Response())
        self.assertEqual(error.exception.status_code, 503)

    def test_empty_dataset_is_valid(self):
        path = self.dataset([])
        with patch.dict(os.environ, {"ELECTRICITY_DATA_PATH": str(path)}):
            data = DemandResponse.model_validate(get_demand(Response())).model_dump()
        self.assertEqual(data["records"], [])
        self.assertIsNone(data["start_month"])

    def test_dataset_is_reread_on_each_request(self):
        path = self.dataset([["VNM", "2025-01", "demand", "", 10, "TWh"]])
        with patch.dict(os.environ, {"ELECTRICITY_DATA_PATH": str(path)}):
            first = get_demand(Response())
            path.write_text(path.read_text(encoding="utf-8-sig").replace(",10,", ",20,"), encoding="utf-8")
            second = get_demand(Response())
        self.assertEqual(first["records"][0]["value"], 10)
        self.assertEqual(second["records"][0]["value"], 20)


if __name__ == "__main__":
    unittest.main()
