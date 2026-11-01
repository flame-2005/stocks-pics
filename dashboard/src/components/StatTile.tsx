export function StatTile({
  label,
  value,
  delta,
  deltaGood,
  hint,
}: {
  label: string;
  value: string;
  delta?: string;
  deltaGood?: boolean | null;
  hint?: string;
}) {
  const deltaClass = deltaGood === null || deltaGood === undefined ? "secondary" : deltaGood ? "delta-up" : "delta-down";
  return (
    <div className="card flex flex-col gap-1">
      <div className="text-xs secondary">{label}</div>
      <div className="text-2xl font-semibold leading-tight">{value}</div>
      {(delta || hint) && (
        <div className={`text-xs ${delta ? deltaClass : "muted"}`}>{delta ?? hint}</div>
      )}
    </div>
  );
}
