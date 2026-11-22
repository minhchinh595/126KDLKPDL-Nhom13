export interface MonthlyDemandRecord {
  country_id: string;
  country: string;
  iso3: string;
  month: string;
  metric: string;
  fuel?: string;
  value: number;
  unit: string;
  cluster?: number;
  clusterLabel?: string;
  growthRateYoY?: number;
}

export interface KPISummary {
  latestMonth: string;
  latestDemand: number;
  latestDemandUnit: string;
  growthRateYoY: number;
  peakDemand: number;
  peakMonth: string;
  averageMonthlyDemand: number;
  totalRecords: number;
  clusteringStatus: string;
  predictionAccuracy: string;
}

export interface MonthlyPatternPoint {
  monthName: string;
  monthIndex: number;
  avgDemand: number;
  minDemand: number;
  maxDemand: number;
}

export interface ClusterSummary {
  clusterId: number;
  name: string;
  description: string;
  count: number;
  percentage: number;
  avgDemand: number;
  color: string;
}

export interface ForecastPoint {
  month: string;
  actualDemand?: number;
  predictedDemand: number;
  lowerBound: number;
  upperBound: number;
}
