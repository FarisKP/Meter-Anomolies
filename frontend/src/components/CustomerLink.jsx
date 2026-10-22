export function CustomerLink({ customer, onSelectCustomer }) {
  return (
    <button
      className="customer-link"
      type="button"
      onClick={() => onSelectCustomer(customer)}
      aria-label={`View usage details for ${customer}`}
    >
      {customer}
    </button>
  )
}
