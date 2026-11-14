import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { isSignedIn, useAuth } from "../hooks/useAuth";

export function Layout() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const signedIn = isSignedIn(me);

  const signOut = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <Link to={signedIn ? "/assistant" : "/"} className="brand" aria-label="KIT home">
          <span className="brand__mark" aria-hidden />
          <span className="brand__name">Knotopian Institute of Technology</span>
          <span className="brand__short">KIT</span>
        </Link>
        <nav className="nav" aria-label="Main">
          {signedIn ? <NavLink to="/assistant">Assistant</NavLink> : <NavLink to="/" end>Home</NavLink>}
          <NavLink to="/history">History</NavLink>
          {signedIn ? (
            <button type="button" className="btn btn--quiet" onClick={() => void signOut()}>
              Log out {me?.name ? `(${me.name.split(" ")[0]})` : ""}
            </button>
          ) : (
            <NavLink to="/login" className="btn btn--quiet">
              Student / staff login
            </NavLink>
          )}
        </nav>
      </header>
      <main id="main" className="main">
        <Outlet />
      </main>
      <footer className="footer">Knotopian Institute of Technology, Coimbatore</footer>
    </div>
  );
}
