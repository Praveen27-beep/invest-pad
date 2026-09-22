/**
 * Trackr+ design system — one import surface.
 *
 * Everything here is styled with inline CSS-variable values rather than Tailwind
 * classes, so a component's appearance is fully described where it is defined and
 * re-themes by swapping the variables in globals.css. See ./tokens.ts for why the
 * exact values live in objects instead of on Tailwind's scale.
 */
export { Icon, ICON_PATHS, type IconName } from "./Icon";
export { Button, IconButton, LinkAction } from "./Button";
export { Card, EmptyState } from "./Card";
export { Badge, type BadgeTone } from "./Badge";
export { Banner } from "./Banner";
export { SegmentedControl, TabBar, type SegmentOption, type TabItem } from "./SegmentedControl";
export {
  LedgerGrid,
  LedgerSecurity,
  LedgerSigned,
  LedgerTag,
  type LedgerColumn,
  type LedgerRow,
} from "./LedgerGrid";
export { DataTable, type DataColumn } from "./DataTable";
export { Modal } from "./Modal";
export { Field, Input, PasswordInput, Select, CopyField, Checkbox } from "./forms";
export { ChartLegend, DonutChart, PieChart, type Slice } from "./charts";
export { BubbleMenu, SlashMenu, type BubbleItem, type SlashGroup, type SlashItem } from "./editor";
export { VintageKpi, VintageXirr, type XirrWindow } from "./VintageKpi";
export { AllocationArcs, type ArcSlice } from "./AllocationArcs";
export { VintageLinePlot, type PlotSeries } from "./VintageLinePlot";
export {
  BarSeries,
  CORRELATION_BANDS,
  DistributionBar,
  Gauge,
  HeatMap,
  MeterRow,
  ScatterPlot,
  type BubblePoint,
  type HeatBand,
} from "./analytics-charts";
export {
  AllocationArcsSkeleton,
  LedgerGridSkeleton,
  LinePlotSkeleton,
  Skeleton,
  VintageKpiSkeleton,
} from "./Skeleton";
export {
  ALLOC_RAMP,
  CHART_COLORS,
  CHART_MONO,
  eyebrow,
  ledgerFig,
  ledgerHead,
  slipFootLabel,
  slipFootRow,
  slipFootValue,
  slipLabel,
  slipNum,
  slipRule,
  slipShell,
} from "./tokens";
