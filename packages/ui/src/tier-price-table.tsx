import { PriceBlock } from "./price-block";

export type TierPriceRow = {
  minQty: number;
  ngwee: number;
};

export type TierPriceTableProps = {
  tiers: TierPriceRow[];
  moq: number;
  quantityHeader: string;
  priceHeader: string;
  moqLabel: string;
  className?: string;
};

function assertIntegerNgwee(value: number): number {
  if (!Number.isInteger(value)) {
    if (process.env.NODE_ENV === "production") {
      console.error(`TierPriceTable: ngwee must be an integer, received ${value}`);
      return Math.round(value);
    }
    throw new TypeError(`TierPriceTable: ngwee must be an integer, received ${value}`);
  }
  return value;
}

export function TierPriceTable({
  tiers,
  moq,
  quantityHeader,
  priceHeader,
  moqLabel,
  className,
}: TierPriceTableProps) {
  const sortedTiers = [...tiers].sort((a, b) => a.minQty - b.minQty);

  return (
    <div className={className} data-testid="tier-price-table">
      <p
        data-testid="tier-moq"
        style={{ margin: "0 0 var(--sp-2)", fontSize: "var(--fs-sm)", color: "var(--text-2)" }}
      >
        {moqLabel}
        <span style={{ fontWeight: 700, color: "var(--text)", marginLeft: "var(--sp-1)" }}>
          {moq}
        </span>
      </p>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "var(--fs-sm)",
        }}
      >
        <thead>
          <tr>
            <th
              scope="col"
              style={{
                textAlign: "left",
                padding: "var(--sp-2)",
                borderBottom: "1px solid var(--border)",
                color: "var(--text-2)",
                fontWeight: 600,
              }}
            >
              {quantityHeader}
            </th>
            <th
              scope="col"
              style={{
                textAlign: "right",
                padding: "var(--sp-2)",
                borderBottom: "1px solid var(--border)",
                color: "var(--text-2)",
                fontWeight: 600,
              }}
            >
              {priceHeader}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedTiers.map((tier) => (
            <tr key={tier.minQty} data-testid={`tier-row-${tier.minQty}`}>
              <td
                style={{
                  padding: "var(--sp-2)",
                  borderBottom: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              >
                {tier.minQty}+
              </td>
              <td
                style={{
                  padding: "var(--sp-2)",
                  borderBottom: "1px solid var(--border)",
                  textAlign: "right",
                }}
              >
                <PriceBlock ngwee={assertIntegerNgwee(tier.ngwee)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
