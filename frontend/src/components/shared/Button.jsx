export default function Button({ children, variant = "default", className = "", ...props }) {
  return (
    <button className={`sf-button ${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}