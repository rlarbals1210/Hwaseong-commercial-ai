export default function ToolHeading({ icon, title, level: Heading = "h3", children }) {
  return <header className="explore-tool-heading">
    <span className="explore-tool-icon material-symbols-outlined" aria-hidden="true">{icon}</span>
    <div><Heading>{title}</Heading>{children}</div>
  </header>;
}
