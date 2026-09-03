// 공무원 화면의 제목 블록.
//
// DashboardPage와 PolicyPage가 거의 같은 함수를 각자 갖고 있었는데, 한쪽에만
// .official-page-header(왼쪽 장식 막대)가 붙어 있어 같은 역할의 두 화면이 다르게
// 보였다. 정의를 한 곳으로 모아 그 차이를 없앤다.
export default function PageHeader({ title, desc }) {
  return (
    <div className="official-page-header" style={{ marginBottom: 24 }}>
      <h1 className="t-h1" style={{ margin: 0 }}>{title}</h1>
      {desc && (
        <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>{desc}</p>
      )}
    </div>
  );
}
