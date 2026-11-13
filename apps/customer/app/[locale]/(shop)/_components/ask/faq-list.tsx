export type FaqListItem = {
  id: string;
  question: string;
  answer: string;
};

export type FaqListProps = {
  title: string;
  items: FaqListItem[];
};

/** Static FAQ answers (delivery / COD / escrow …) as native, zero-JS disclosures. */
export function FaqList({ title, items }: FaqListProps) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby="ask-faq-title" className="space-y-2" data-testid="ask-faq">
      <h2 id="ask-faq-title" className="text-sm font-semibold text-text">
        {title}
      </h2>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={item.id}>
            <details
              open={index === 0}
              className="rounded-lg border border-border bg-surface p-3"
              data-testid="ask-faq-item"
            >
              <summary className="min-h-11 cursor-pointer text-sm font-medium text-text">
                {item.question}
              </summary>
              <p className="pt-1 text-sm text-text-2">{item.answer}</p>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
