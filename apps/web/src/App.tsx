import styled from "@emotion/styled";

const Shell = styled.main`
  min-height: 100vh;
  display: grid;
  place-content: center;
  padding: 2rem;
`;

export function App() {
  return (
    <Shell>
      <p className="eyebrow">OPEN SOURCE / SELF HOSTED</p>
      <h1>
        Memory needs
        <br />
        <em>structure.</em>
      </h1>
      <p className="lede">
        OpenGraphRAG foundation is online. Build searchable context from vectors and knowledge
        graphs.
      </p>
      <a href="/api/docs">
        Explore the API <span aria-hidden="true">-&gt;</span>
      </a>
    </Shell>
  );
}
