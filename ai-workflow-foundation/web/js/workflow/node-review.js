import { nodeRole } from "./transitions.js";

export function defaultReviewInputs(node) {
  const id = node?.id || "self";
  return { primary_output: `artifact.${id}` };
}

export function normalizeNodeReview(node) {
  if (!node) {
    return {
      mode: "auto",
      level: "optional",
      inputs: {},
      skill: null,
      criteria: "",
      checklist: [],
    };
  }
  if (nodeRole(node) === "review") {
    return {
      mode: node.approval?.mode || "human",
      level: node.approval?.level || "required",
      inputs: node.inputs || {},
      skill: node.review?.skill || null,
      criteria: node.review?.criteria || "",
      checklist: node.review?.checklist || [],
    };
  }
  const review = node.review || {};
  return {
    mode: review.mode || node.approval?.mode || "auto",
    level: review.level || node.approval?.level || "optional",
    inputs: review.inputs || defaultReviewInputs(node),
    skill: review.skill || null,
    criteria: review.criteria || "",
    checklist: Array.isArray(review.checklist) ? review.checklist : [],
  };
}

export function syncReviewFieldsToNode(node, fields) {
  if (!node) return;
  const review = {
    mode: fields.mode || "auto",
    level: fields.level || "optional",
    inputs: fields.inputs || defaultReviewInputs(node),
    criteria: fields.criteria || "",
    checklist: fields.checklist || [],
  };
  if (fields.skill) review.skill = fields.skill;
  node.review = review;
  node.approval = { mode: review.mode, level: review.level };
  if (nodeRole(node) === "review") {
    node.inputs = review.inputs;
  }
}

export function reviewChecklistText(checklist) {
  return (checklist || []).join("\n");
}

export function parseReviewChecklist(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function expectedReviewLabel(node) {
  const review = normalizeNodeReview(node);
  const entries = Object.entries(review.inputs || {});
  if (!entries.length) return "本节点产出";
  return entries.map(([key, value]) => `${key}: ${value}`).join(" · ");
}
