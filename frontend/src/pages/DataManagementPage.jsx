import { Fragment, useCallback, useEffect, useId, useRef, useState } from "react";
import { apiFetchJson, describeApiError } from "../lib/api";


const formatBytes = (bytes) => {
  const value = Number(bytes);
  if (!Number.isFinite(value)) return "—";
  if (value < 1024) return `${value.toLocaleString()} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
};

const formatDateTime = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

function validationSummary(upload) {
  const validation = upload?.validation ?? {};
  if (upload?.dataset_type === "card_sales") {
    return [
      validation.row_count != null ? `${Number(validation.row_count).toLocaleString()}행` : null,
      validation.month_start && validation.month_end
        ? `${validation.month_start}~${validation.month_end}`
        : null,
      validation.area_code_count != null ? `행정동 코드 ${validation.area_code_count}개` : null,
      validation.industry_code_count != null ? `업종 코드 ${validation.industry_code_count}개` : null,
    ].filter(Boolean);
  }
  return [
    validation.industry_code_count != null ? `업종 코드 ${validation.industry_code_count}개` : null,
    validation.duplicate_code_count != null ? `중복 ${validation.duplicate_code_count}개` : null,
  ].filter(Boolean);
}

function UploadCard({ dataset, onUploaded }) {
  const inputId = useId();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [state, setState] = useState({ type: "idle", message: "" });

  const selectFile = (nextFile) => {
    if (!nextFile) return;
    const suffix = `.${nextFile.name.split(".").pop()?.toLowerCase()}`;
    if (!dataset.accepted_extensions.includes(suffix)) {
      setFile(null);
      setState({
        type: "error",
        message: `${dataset.accepted_extensions.join(", ")} 파일만 선택할 수 있습니다.`,
      });
      return;
    }
    if (nextFile.size > dataset.max_size_mb * 1024 * 1024) {
      setFile(null);
      setState({ type: "error", message: `${dataset.max_size_mb}MB 이하 파일을 선택해주세요.` });
      return;
    }
    setFile(nextFile);
    setState({ type: "idle", message: "" });
  };

  const upload = async () => {
    if (!file || state.type === "uploading") return;
    setState({ type: "uploading", message: "파일을 올리고 형식을 검증하는 중입니다…" });
    try {
      const params = new URLSearchParams({ filename: file.name });
      const result = await apiFetchJson(
        `/api/data-management/uploads/${dataset.dataset_type}?${params}`,
        {
          method: "POST",
          headers: { "Content-Type": file.type || "application/octet-stream" },
          body: file,
        },
      );
      setState({ type: "success", message: "파일 형식 검증을 통과했습니다." });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded(result);
    } catch (error) {
      setState({
        type: "error",
        message: error?.message && !error.message.startsWith("API request failed")
          ? error.message
          : describeApiError(error),
      });
    }
  };

  const latest = dataset.latest_upload;
  const latestSummary = validationSummary(latest);

  return (
    <article className="data-upload-card card">
      <header className="data-upload-card-head">
        <span className="data-upload-icon material-symbols-outlined" aria-hidden="true">
          {dataset.dataset_type === "card_sales" ? "payments" : "account_tree"}
        </span>
        <div>
          <div className="t-title">{dataset.title}</div>
          <p className="t-body-sm">{dataset.description}</p>
        </div>
      </header>

      <div className="data-upload-spec">
        <span className="t-eyebrow">기대 파일</span>
        <code>{dataset.expected_filename}</code>
        <span className="t-caption">{dataset.required_columns.join(" · ")}</span>
      </div>

      <label
        htmlFor={inputId}
        className={`data-upload-dropzone${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          selectFile(event.dataTransfer.files?.[0]);
        }}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={dataset.accepted_extensions.join(",")}
          onChange={(event) => selectFile(event.target.files?.[0])}
        />
        <span className="material-symbols-outlined" aria-hidden="true">
          {file ? "draft" : "upload_file"}
        </span>
        {file ? (
          <span className="data-upload-selected">
            <b>{file.name}</b>
            <small>{formatBytes(file.size)} · 다른 파일을 고르려면 이 영역을 다시 누르세요</small>
          </span>
        ) : (
          <span>
            <b>파일을 놓거나 눌러서 선택</b>
            <small>{dataset.accepted_extensions.join(", ")} · 최대 {dataset.max_size_mb}MB</small>
          </span>
        )}
      </label>

      <button
        type="button"
        className={`btn-primary data-upload-submit${state.type === "uploading" ? " is-uploading" : ""}`}
        disabled={!file || state.type === "uploading"}
        onClick={upload}
      >
        <span className="material-symbols-outlined" aria-hidden="true">
          {state.type === "uploading" ? "progress_activity" : "fact_check"}
        </span>
        {state.type === "uploading" ? "검증 중…" : "업로드 후 검증"}
      </button>

      {state.message && (
        <div className={`data-upload-feedback is-${state.type}`} role={state.type === "error" ? "alert" : "status"}>
          <span className="material-symbols-outlined" aria-hidden="true">
            {state.type === "error" ? "error" : state.type === "success" ? "check_circle" : "hourglass_top"}
          </span>
          {state.message}
        </div>
      )}

      <div className="data-upload-latest">
        <div className="data-upload-latest-title">
          <span>최근 업로드</span>
          {latest && <span className="badge data-status-pending">검증 완료 · 반영 대기</span>}
        </div>
        {latest ? (
          <>
            <b>{latest.original_filename}</b>
            <span className="t-caption">
              {formatDateTime(latest.uploaded_at_utc)} · {formatBytes(latest.size_bytes)}
            </span>
            {latestSummary.length > 0 && (
              <span className="t-caption data-upload-validation">{latestSummary.join(" · ")}</span>
            )}
          </>
        ) : (
          <span className="t-caption">아직 업로드한 파일이 없습니다.</span>
        )}
      </div>
    </article>
  );
}

const formatCount = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ko-KR") : "—";
};

function CurrentDataSummary({ data }) {
  const hasData = Boolean(data) && data.latest_quarter_code != null;
  const metrics = [
    {
      key: "latest_quarter",
      icon: "event_available",
      label: "최신 반영 분기",
      value: data?.latest_quarter_label ?? "—",
      unit: "",
      accent: true,
    },
    { key: "quarter_count", icon: "database", label: "적재된 분기", value: formatCount(data?.quarter_count), unit: "개" },
    { key: "area_count", icon: "location_on", label: "행정동", value: formatCount(data?.area_count), unit: "개" },
    { key: "industry_count", icon: "storefront", label: "업종", value: formatCount(data?.industry_count), unit: "개" },
    {
      key: "cell_count",
      icon: "grid_view",
      label: "분석 셀",
      value: formatCount(data?.analysis_cell_count),
      unit: "개",
      // 조기경보·등급 기준선은 표본충분 셀만 모수로 쓴다. 총 레코드 수만 적으면
      // 두 화면이 서로 다른 수를 "셀"이라 부르게 되므로 함께 적는다.
      sub: data?.sample_sufficient_cell_count != null
        ? `표본충분 ${formatCount(data.sample_sufficient_cell_count)}개`
        : null,
    },
  ];

  return (
    <section className="data-current card" aria-label="현재 서비스 반영 데이터">
      <div className="data-current-head">
        <div>
          <h2 className="t-title">현재 서비스 반영 데이터</h2>
          <p className="t-body-sm">지금 화면과 분석이 실제로 사용하고 있는 데이터입니다.</p>
        </div>
        <span className="badge data-status-live">
          <span className="material-symbols-outlined" aria-hidden="true">check_circle</span>
          운영 반영 중
        </span>
      </div>

      {hasData ? (
        <dl className="data-current-grid">
          {metrics.map((metric) => (
            <div key={metric.key} className={`data-current-metric${metric.accent ? " is-accent" : ""}`}>
              <dt>
                <span className="material-symbols-outlined" aria-hidden="true">{metric.icon}</span>
                {metric.label}
              </dt>
              <dd>
                <b>{metric.value}</b>
                {metric.unit && <small>{metric.unit}</small>}
              </dd>
              {metric.sub && <span className="data-current-sub">{metric.sub}</span>}
            </div>
          ))}
        </dl>
      ) : (
        <div className="data-current-empty">
          <span className="material-symbols-outlined" aria-hidden="true">inbox</span>
          <div>
            <b>반영된 데이터 없음</b>
            <span>운영 DB에 적재된 분기가 아직 없습니다.</span>
          </div>
        </div>
      )}

      <p className="data-current-note">
        <span className="material-symbols-outlined" aria-hidden="true">info</span>
        업로드 후 반영 대기 중인 파일은 포함되지 않은 운영 데이터 기준입니다.
      </p>
    </section>
  );
}

// 운영 반영 배치와 업로드 대기 파일을 한 표에 섞되, 시각으로만 정렬하고 상태
// 배지로 구분한다. 두 표로 나누면 "무엇이 먼저 들어왔는가"를 눈으로 못 쫓는다.
function historyRows(batches, uploads) {
  const fromBatches = (batches ?? []).map((batch) => ({
    key: `batch:${batch.batch_key}`,
    at: batch.imported_at,
    title: batch.source_name,
    detail: [batch.quarter_start_label, batch.quarter_end_label].filter(Boolean).join(" ~ "),
    detailSub: batch.method_version,
    result: [
      batch.row_count != null ? `${Number(batch.row_count).toLocaleString("ko-KR")}행` : null,
      batch.quality_notes,
    ].filter(Boolean).join(" · "),
    actor: "파이프라인 적재",
    status: { label: "운영 반영 완료", className: "data-status-live" },
    kind: "batch",
    batchKey: batch.batch_key,
  }));
  const fromUploads = (uploads ?? []).map((upload) => ({
    key: `upload:${upload.upload_id}`,
    at: upload.uploaded_at_utc,
    title: upload.dataset_title,
    detail: upload.original_filename,
    detailSub: formatBytes(upload.size_bytes),
    result: validationSummary(upload).join(" · ") || "형식 검증 완료",
    actor: upload.uploaded_by,
    status: { label: "반영 대기", className: "data-status-pending" },
    kind: "upload",
    upload,
  }));
  return [...fromBatches, ...fromUploads].sort(
    (a, b) => String(b.at ?? "").localeCompare(String(a.at ?? "")),
  );
}

function DetailGrid({ items }) {
  const visible = items.filter((item) => item.value !== null && item.value !== undefined && item.value !== "");
  if (!visible.length) return null;
  return (
    <dl className="data-history-detail-grid">
      {visible.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd className={item.mono ? "is-mono" : undefined}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function UploadDetail({ upload }) {
  const v = upload?.validation ?? {};
  const pct = (part, whole) =>
    whole ? ` (${((Number(part) / Number(whole)) * 100).toFixed(3)}%)` : "";
  return (
    <>
      <DetailGrid
        items={[
          { label: "저장 파일명", value: upload.stored_filename, mono: true },
          { label: "크기", value: formatBytes(upload.size_bytes) },
          { label: "업로더", value: upload.uploaded_by },
          { label: "상태", value: "형식 검증 통과 · 운영 미반영" },
          { label: "SHA-256", value: upload.sha256, mono: true },
        ]}
      />
      <DetailGrid
        items={[
          { label: "인코딩", value: v.encoding },
          {
            label: "행 수",
            value: v.row_count != null ? `${Number(v.row_count).toLocaleString("ko-KR")}행` : null,
          },
          {
            label: "형식 오류 행",
            value: v.invalid_row_count != null
              ? `${Number(v.invalid_row_count).toLocaleString("ko-KR")}행${pct(v.invalid_row_count, v.row_count)}`
              : null,
          },
          {
            label: "커버 기간",
            value: v.month_start && v.month_end
              ? `${v.month_start}~${v.month_end}${v.month_count ? ` (${v.month_count}개월)` : ""}`
              : null,
          },
          { label: "행정동 코드", value: v.area_code_count != null ? `${v.area_code_count}개` : null },
          { label: "업종 코드", value: v.industry_code_count != null ? `${v.industry_code_count}개` : null },
          { label: "중복 코드", value: v.duplicate_code_count != null ? `${v.duplicate_code_count}개` : null },
          { label: "시트", value: v.sheet },
        ]}
      />
    </>
  );
}

const pctText = (value) => (value == null ? null : `${Number(value).toFixed(2)}%`);

function BatchDetail({ state }) {
  if (state?.status === "loading") {
    return (
      <div className="data-history-detail-loading">
        <span className="material-symbols-outlined" aria-hidden="true">progress_activity</span>
        상세를 불러오는 중…
      </div>
    );
  }
  if (state?.status === "error") {
    return <div className="data-history-detail-error" role="alert">{state.message}</div>;
  }
  const d = state?.data;
  if (!d) return null;
  const t = d.thresholds;
  return (
    <>
      <DetailGrid
        items={[
          {
            label: "적재 범위",
            value: [d.quarter_start_label, d.quarter_end_label].filter(Boolean).join(" ~ ")
              + (d.quarter_count ? ` · ${d.quarter_count}개 분기` : ""),
          },
          { label: "방법 버전", value: d.method_version, mono: true },
          { label: "배치 키", value: d.batch_key, mono: true },
          {
            label: "적재 행 수",
            value: d.row_count != null ? `${Number(d.row_count).toLocaleString("ko-KR")}행` : null,
          },
          { label: "최신 분기 구성", value: `행정동 ${d.area_count}개 · 업종 ${d.industry_count}개` },
          {
            label: "점포 격자",
            value: d.store_cluster_count
              ? `${Number(d.store_cluster_count).toLocaleString("ko-KR")}칸`
              : null,
          },
          { label: "품질 메모", value: d.quality_notes },
        ]}
      />

      {t && (
        <div className="data-history-detail-block">
          <div className="data-history-detail-title">
            이 배치가 사용한 기준선{t.quarter_label ? ` · ${t.quarter_label}` : ""}
          </div>
          <DetailGrid
            items={[
              { label: "평균 폐업률", value: pctText(t.avg_closure_rate_pct) },
              { label: "주의 경계", value: pctText(t.caution_threshold_pct) },
              { label: "위험 경계", value: pctText(t.danger_threshold_pct) },
              { label: "동 평균 위험업종비율", value: pctText(t.area_ratio_avg_pct) },
              { label: "동 위험 경계", value: pctText(t.area_ratio_danger_pct) },
              { label: "표본 최소 점포수", value: t.sample_min != null ? `${t.sample_min}개` : null },
              { label: "누적 창", value: t.window_quarters != null ? `${t.window_quarters}분기` : null },
              { label: "산출 방법", value: t.method, mono: true },
            ]}
          />
        </div>
      )}

      {d.quarters?.length > 0 && (
        <div className="data-history-detail-block">
          <div className="data-history-detail-title">분기별 셀 수</div>
          <ul className="data-history-quarters">
            {d.quarters.map((q) => (
              <li key={q.quarter_code}>
                <span>{q.quarter_label ?? q.quarter_code}</span>
                <b>{Number(q.cell_count).toLocaleString("ko-KR")}</b>
                <small>표본충분 {Number(q.sample_sufficient_cell_count).toLocaleString("ko-KR")}</small>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function UploadHistory({ batches, uploads }) {
  const rows = historyRows(batches, uploads);
  const [openKey, setOpenKey] = useState(null);
  // 펼친 배치의 상세는 클릭할 때 한 번만 받아 캐시한다. 접었다 펴도 다시 안 부른다.
  const [details, setDetails] = useState({});

  const toggle = (row) => {
    if (openKey === row.key) {
      setOpenKey(null);
      return;
    }
    setOpenKey(row.key);
    if (row.kind !== "batch" || details[row.key]) return;
    setDetails((prev) => ({ ...prev, [row.key]: { status: "loading" } }));
    apiFetchJson(`/api/data-management/batches/${encodeURIComponent(row.batchKey)}`)
      .then((data) => setDetails((prev) => ({ ...prev, [row.key]: { status: "ready", data } })))
      .catch((error) =>
        setDetails((prev) => ({
          ...prev,
          [row.key]: { status: "error", message: describeApiError(error) },
        })),
      );
  };

  return (
    <section className="data-upload-history card">
      <div className="data-upload-section-head">
        <div>
          <h2 className="t-title">데이터 반영·업로드 이력</h2>
          <p className="t-body-sm">
            운영에 반영된 적재 배치와, 올렸지만 아직 반영되지 않은 파일을 함께 보여줍니다.
            줄을 누르면 자세한 내역이 열립니다.
          </p>
        </div>
        <span className="badge badge-neutral">{rows.length}건</span>
      </div>
      {rows.length ? (
        <div className="data-upload-table-wrap">
          <table className="data-upload-table">
            <thead>
              <tr>
                <th>데이터</th>
                <th>대상</th>
                <th>내용</th>
                <th>시각</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const open = openKey === row.key;
                return (
                  <Fragment key={row.key}>
                    <tr className={`data-history-row${open ? " is-open" : ""}`}>
                      <td>
                        <button
                          type="button"
                          className="data-history-toggle"
                          aria-expanded={open}
                          onClick={() => toggle(row)}
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            {open ? "expand_more" : "chevron_right"}
                          </span>
                          <b>{row.title}</b>
                        </button>
                      </td>
                      <td>
                        <span>{row.detail || "—"}</span>
                        {row.detailSub && <small>{row.detailSub}</small>}
                      </td>
                      <td>{row.result || "—"}</td>
                      <td>
                        <span>{formatDateTime(row.at)}</span>
                        <small>{row.actor}</small>
                      </td>
                      <td><span className={`badge ${row.status.className}`}>{row.status.label}</span></td>
                    </tr>
                    {open && (
                      <tr className="data-history-detail-row">
                        <td colSpan={5}>
                          <div className="data-history-detail">
                            {row.kind === "batch"
                              ? <BatchDetail state={details[row.key]} />
                              : <UploadDetail upload={row.upload} />}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="data-upload-empty">
          <span className="material-symbols-outlined" aria-hidden="true">history</span>
          <span>반영·업로드 이력이 없습니다.</span>
        </div>
      )}
    </section>
  );
}

export default function DataManagementPage() {
  const [payload, setPayload] = useState({ current_data: null, operational_batches: [], datasets: [], uploads: [], notice: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const result = await apiFetchJson("/api/data-management");
      setPayload(result);
      setError("");
    } catch (loadError) {
      setError(describeApiError(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    apiFetchJson("/api/data-management")
      .then((result) => {
        if (!active) return;
        setPayload(result);
        setError("");
      })
      .catch((loadError) => {
        if (active) setError(describeApiError(loadError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  const handleUploaded = () => refresh();

  return (
    <div className="official-page data-management-page">
      <header className="official-page-header data-management-header">
        <h1 className="t-h1">데이터 관리</h1>
        <p className="t-body-sm">
          API로 받지 못하는 카드매출 자료를 올리고, 반영 전 파일 형식을 검증합니다.
        </p>
      </header>

      <div className="data-management-safety" role="note">
        <span className="material-symbols-outlined" aria-hidden="true">verified_user</span>
        <div>
          <b>업로드만으로 현재 지표가 바뀌지 않습니다.</b>
          <span>{payload.notice || "검증한 파일은 반영 대기 영역에 보관하고, 재학습·DB 적재는 별도로 진행합니다."}</span>
        </div>
      </div>

      {error && <div className="data-management-error" role="alert">{error}</div>}

      {loading ? (
        <div className="data-management-loading">
          <span className="material-symbols-outlined" aria-hidden="true">progress_activity</span>
          데이터 현황을 불러오는 중…
        </div>
      ) : (
        <>
          <CurrentDataSummary data={payload.current_data} />
          <section className="data-upload-grid" aria-label="수동 데이터 업로드">
            {payload.datasets.map((dataset) => (
              <UploadCard key={dataset.dataset_type} dataset={dataset} onUploaded={handleUploaded} />
            ))}
          </section>
          <UploadHistory batches={payload.operational_batches ?? []} uploads={payload.uploads ?? []} />
        </>
      )}
    </div>
  );
}
