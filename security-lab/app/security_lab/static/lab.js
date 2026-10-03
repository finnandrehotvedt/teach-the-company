(() => {
  const buttons = [...document.querySelectorAll("[data-scenario]")];
  const run = document.querySelector("[data-run]");
  if (!run) return;

  const approval = document.querySelector("[data-approve]");
  const receipt = document.querySelector("[data-receipt]");
  const state = { scenario: "minimum" };
  const label = (value) => value.replaceAll("_", " ");

  function setFields(values, denied = false) {
    const target = document.querySelector("[data-request-fields]");
    target.replaceChildren(...values.map((value) => {
      const span = document.createElement("span");
      span.className = "field" + (denied ? " denied" : "");
      span.textContent = label(value);
      return span;
    }));
  }

  function select(scenario) {
    state.scenario = scenario;
    buttons.forEach((button) => button.classList.toggle("active", button.dataset.scenario === scenario));
    receipt.hidden = true;
    approval.hidden = true;
    document.querySelector("[data-status]").textContent = "Ready for a deterministic replay.";
  }

  async function evaluate(ownerApproved = false) {
    run.disabled = true;
    approval.disabled = true;
    document.querySelector("[data-status]").textContent = "The independent gateway is checking the manifest…";
    try {
      const response = await fetch("/api/evaluate/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: state.scenario, owner_approved: ownerApproved }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The policy request failed.");

      document.querySelector("[data-request-title]").textContent = data.scenario_label;
      document.querySelector("[data-request-reason]").textContent = data.stated_reason;
      setFields(data.requested_fields, data.decision === "denied");
      document.querySelector("[data-decision]").textContent = label(data.decision);
      document.querySelector("[data-decision-reason]").textContent = data.decision_reason;
      document.querySelector("[data-result-state]").textContent = label(data.result_state);
      document.querySelector("[data-result]").textContent = data.result;
      document.querySelector("[data-released-count]").textContent = data.released_fields.length + " fields released";
      document.querySelector("[data-withheld-count]").textContent = data.withheld_fields.length + " withheld";
      const light = document.querySelector("[data-gateway-light]");
      light.className = "gateway-light " + (data.decision.startsWith("approved") ? "approved" : data.decision === "denied" ? "denied" : "");

      document.querySelector("[data-receipt-id]").textContent = data.receipt_id;
      document.querySelector("[data-receipt-requested]").textContent = data.requested_fields.map(label).join(", ");
      document.querySelector("[data-receipt-released]").textContent = data.released_fields.length ? data.released_fields.map(label).join(", ") : "None";
      document.querySelector("[data-receipt-withheld]").textContent = data.withheld_fields.map(label).join(", ");
      document.querySelector("[data-receipt-memory]").textContent = data.memory_policy;
      document.querySelector("[data-receipt-result]").textContent = data.result;
      document.querySelector("[data-share]").href = data.share_url;
      receipt.hidden = false;
      approval.hidden = data.decision !== "owner_approval_required";
      document.querySelector("[data-status]").textContent = "Decision complete. The receipt is inspectable below.";
      receipt.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      document.querySelector("[data-status]").textContent = error.message;
    } finally {
      run.disabled = false;
      approval.disabled = false;
    }
  }

  buttons.forEach((button) => button.addEventListener("click", () => select(button.dataset.scenario)));
  run.addEventListener("click", () => evaluate(false));
  approval.addEventListener("click", () => evaluate(true));
})();
