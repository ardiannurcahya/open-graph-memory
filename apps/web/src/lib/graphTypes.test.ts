import { describe, it, expect } from "vitest";
import { classifyEntityType } from "./graphTypes";

describe("classifyEntityType", () => {
  it("classifies person variants", () => {
    expect(classifyEntityType("person")).toBe("person");
    expect(classifyEntityType("author")).toBe("person");
    expect(classifyEntityType("Researcher")).toBe("person");
  });

  it("classifies org variants", () => {
    expect(classifyEntityType("organization")).toBe("org");
    expect(classifyEntityType("company")).toBe("org");
    expect(classifyEntityType("institution")).toBe("org");
  });

  it("classifies tech variants", () => {
    expect(classifyEntityType("technology")).toBe("tech");
    expect(classifyEntityType("framework")).toBe("tech");
  });

  it("classifies concept variants", () => {
    expect(classifyEntityType("concept")).toBe("concept");
    expect(classifyEntityType("method")).toBe("concept");
  });

  it("classifies document variants", () => {
    expect(classifyEntityType("document")).toBe("document");
    expect(classifyEntityType("paper")).toBe("document");
  });

  it("returns unknown for unrecognized types", () => {
    expect(classifyEntityType("")).toBe("unknown");
    expect(classifyEntityType("xyz")).toBe("unknown");
  });
});
