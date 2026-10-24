"use strict";
const $ = (selector) => document.querySelector(selector);
let trip, step = "flight", aiConfigured = false, saving = false;
let activeSearch = 0;
const labels = {flight: "항공권 비교", hotel: "호텔 비교", itinerary: "일정 구성", restaurants: "식당 검색"};

function notify(message, error = false) {
  $("#notice").textContent = message;
  $("#notice").classList.toggle("error", error);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "요청에 실패했습니다.");
    error.status = response.status;
    throw error;
  }
  return data;
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function allowed(target) {
  if (!trip) return false;
  return target === "flight" || (target === "hotel" && !!trip.flight) ||
    (target === "itinerary" && !!trip.hotel) || (target === "restaurants" && trip.activities.length > 0);
}
function fill(form, data) {
  form.reset();
  if (!data) return;
  for (const [key, value] of Object.entries(data)) {
    const input = form.elements.namedItem(key);
    if (input) input.value = ["start", "end", "arrival_time", "departure_time"].includes(key)
      ? value.slice(0, 5) : value;
  }
}
function invalidateAnswer() {
  activeSearch++;
  $("#answer").hidden = true;
  $("#ask").disabled = !aiConfigured;
  $("#ask").textContent = "검색·추천 받기";
}
function selectStep(target) {
  if (!allowed(target)) return;
  if (step !== target) {
    invalidateAnswer();
    $("#question").value = "";
  }
  step = target;
  document.querySelectorAll(".step").forEach(node => { node.hidden = node.id !== step; });
  document.querySelectorAll("[data-step]").forEach(button => {
    button.classList.toggle("active", button.dataset.step === step);
    button.disabled = !allowed(button.dataset.step);
    if (button.dataset.step === step) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  $("#agent-heading").textContent = `${labels[step]} 도우미`;
  $("#agent-context").textContent = {
    flight: "출발지, 목적지, 날짜, 인원, 예산과 원하는 조건을 알려주세요.",
    hotel: "확정된 항공 일정에 맞춰 숙소를 비교합니다. 인원·객실 수·예산을 알려주세요.",
    itinerary: "항공 시간과 호텔 위치를 바탕으로 동선을 제안합니다. 추천 내용을 일정표에 추가하세요.",
    restaurants: "선택한 일정의 시간·위치에 맞춰 찾습니다. 음식 취향·예산·알레르기를 알려주세요."
  }[step];
}
function editActivity(item) {
  selectStep("itinerary");
  fill($("#activity-form"), item);
  $("#activity-heading").textContent = "일정 수정";
  $("#cancel-edit").hidden = false;
  $("#activity-form").scrollIntoView({behavior: "smooth", block: "start"});
}
function resetActivityForm() {
  $("#activity-form").reset();
  $("#activity-form").elements.namedItem("id").value = "";
  $("#activity-heading").textContent = "일정 추가";
  $("#cancel-edit").hidden = true;
}
function mealContext() {
  invalidateAnswer();
  const item = trip.activities.find(a => a.id === $("#meal-activity").value);
  $("#meal-context").textContent = item
    ? `${item.day} · ${item.start.slice(0, 5)}–${item.end.slice(0, 5)}\n${item.title}\n${item.area}` : "일정을 먼저 추가하세요.";
}
function render() {
  fill($("#flight-form"), trip.flight);
  fill($("#hotel-form"), trip.hotel);
  if (trip.flight) {
    const f = trip.flight;
    $("#flight-summary").textContent = `${f.destination} · ${f.arrival_date} 도착 → ${f.departure_date} 출발`;
    for (const name of ["check_in", "check_out"]) {
      const input = $("#hotel-form").elements.namedItem(name);
      input.min = f.arrival_date;
      input.max = f.departure_date;
    }
    if (!trip.hotel) {
      $("#hotel-form").elements.namedItem("check_in").value = f.arrival_date;
      $("#hotel-form").elements.namedItem("check_out").value = f.departure_date;
    }
    $("#activity-form").elements.namedItem("day").min = f.arrival_date;
    $("#activity-form").elements.namedItem("day").max = f.departure_date;
  }
  $("#hotel-summary").textContent = trip.hotel ? `${trip.hotel.name} · ${trip.hotel.area} 기준으로 하루를 구성하세요.` : "";
  $("#schedule").replaceChildren();
  for (const item of trip.activities) {
    const card = element("article", undefined, "activity");
    card.append(element("p", `${item.day} · ${item.start.slice(0, 5)}–${item.end.slice(0, 5)}`),
      element("h3", item.title), element("p", item.area), element("p", item.notes));
    const actions = element("div", undefined, "actions");
    const edit = element("button", "수정", "quiet");
    edit.onclick = () => editActivity(item);
    const remove = element("button", "삭제", "quiet");
    remove.onclick = () => {
      if (confirm(`'${item.title}' 일정을 삭제할까요?`)) {
        mutate("activities", trip.activities.filter(a => a.id !== item.id), "itinerary");
      }
    };
    const meal = element("button", "이 일정 근처 식당", "quiet");
    meal.onclick = () => {
      selectStep("restaurants");
      $("#meal-activity").value = item.id;
      mealContext();
    };
    actions.append(edit, remove, meal);
    card.append(actions);
    $("#schedule").append(card);
  }
  if (!trip.activities.length) $("#schedule").append(element("p", "아직 일정이 없어요. 관광·이동·식사 시간을 추가해보세요."));
  const previous = $("#meal-activity").value;
  $("#meal-activity").replaceChildren(...trip.activities.map(item => {
    const option = element("option", `${item.day} ${item.start.slice(0, 5)} · ${item.title}`);
    option.value = item.id;
    return option;
  }));
  if (trip.activities.some(a => a.id === previous)) $("#meal-activity").value = previous;
  mealContext();
  selectStep(allowed(step) ? step : trip.stage);
}
async function mutate(action, data, nextStep) {
  if (saving) return;
  saving = true;
  try {
    trip = await api(`/api/trips/${trip.id}/${action}`, {version: trip.version, data});
    step = nextStep;
    resetActivityForm();
    render();
    notify("저장했습니다. " + (aiConfigured ? "" : "AI 검색은 환경 설정에 API 키를 입력하면 사용할 수 있어요."));
  } catch (error) { notify(error.message, true); }
  finally { saving = false; }
}
$("#steps").addEventListener("click", event => {
  const button = event.target.closest("[data-step]");
  if (button) selectStep(button.dataset.step);
});
for (const action of ["flight", "hotel"]) {
  $(`#${action}-form`).onsubmit = event => {
    event.preventDefault();
    if (!trip) return;
    if ((action === "flight" && trip.hotel) || (action === "hotel" && trip.activities.length)) {
      if (!confirm("확정 정보를 변경하면 이후 단계의 계획이 초기화됩니다. 계속할까요?")) return;
    }
    mutate(action, Object.fromEntries(new FormData(event.target)), action === "flight" ? "hotel" : "itinerary");
  };
}
$("#activity-form").onsubmit = event => {
  event.preventDefault();
  if (!trip) return;
  const data = Object.fromEntries(new FormData(event.target));
  if (!data.id) data.id = crypto.randomUUID();
  const activities = trip.activities.filter(a => a.id !== data.id);
  activities.push(data);
  mutate("activities", activities, "itinerary");
};
$("#cancel-edit").onclick = resetActivityForm;
$("#meal-activity").onchange = mealContext;
$("#edit-meal").onclick = () => {
  const item = trip.activities.find(a => a.id === $("#meal-activity").value);
  if (item) editActivity(item);
};
$("#agent-form").onsubmit = async event => {
  event.preventDefault();
  if (!trip || !aiConfigured) return;
  const token = ++activeSearch, version = trip.version;
  $("#ask").disabled = true;
  $("#ask").textContent = "찾아보는 중…";
  $("#answer").hidden = true;
  try {
    const result = await api(`/api/trips/${trip.id}/advice`, {
      stage: step, message: $("#question").value, version,
      activity_id: step === "restaurants" ? $("#meal-activity").value : null
    });
    if (token !== activeSearch || version !== trip.version) return;
    $("#answer-text").textContent = result.text;
    $("#answer-meta").textContent = `조회 ${new Date(result.checked_at).toLocaleString("ko-KR")}`;
    $("#sources").replaceChildren(...result.sources.map(source => {
      const li = element("li"), a = element("a", source.title || source.url);
      a.href = source.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      li.append(a); return li;
    }));
    $("#answer").hidden = false;
    notify("추천을 확인하고 원하는 후보를 직접 계획에 반영하세요.");
  } catch (error) {
    if (token === activeSearch) notify(error.message, true);
  } finally {
    if (token === activeSearch) {
      $("#ask").disabled = false;
      $("#ask").textContent = "검색·추천 받기";
    }
  }
};
async function newTrip() {
  trip = await api("/api/trips", {});
  localStorage.setItem("travel-trip-id", trip.id);
  step = "flight";
  resetActivityForm();
  render();
}
$("#new-trip").onclick = async () => {
  if (!confirm("새 여행을 만들까요? 현재 여행은 서버에 보관되지만 이 화면은 새 여행으로 전환됩니다.")) return;
  try { await newTrip(); notify("새 여행을 시작합니다."); }
  catch (error) { notify(error.message, true); }
};
(async () => {
  try {
    const health = await api("/api/health");
    aiConfigured = health.ai_configured;
    const id = localStorage.getItem("travel-trip-id");
    if (id) {
      try { trip = await api(`/api/trips/${encodeURIComponent(id)}`); }
      catch (error) { if (error.status !== 404) throw error; }
    }
    if (!trip) await newTrip();
    else { step = trip.stage; render(); }
    notify(aiConfigured ? "여행을 불러왔습니다. 순서대로 계획해보세요." :
      "일정 편집·저장은 바로 사용할 수 있어요. AI 검색은 환경 설정에 TRAVEL_AGENT_API_KEY를 입력한 뒤 서버를 다시 시작하세요.");
  } catch (error) { notify(`시작하지 못했습니다: ${error.message}`, true); }
})();
