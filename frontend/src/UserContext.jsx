import { createContext, useContext, useEffect, useState } from "react";
import { getMe } from "./api";

const UserContext = createContext(null);

const DEFAULT_VALUE = {
  user: null,
  role: "campaign_builder",
  isAdmin: false,
  canBuild: true,
  isViewer: false,
};

export function UserProvider({ children }) {
  const [userInfo, setUserInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMe()
      .then(setUserInfo)
      .catch(() => setUserInfo(null))
      .finally(() => setLoading(false));
  }, []);

  const value = loading
    ? DEFAULT_VALUE
    : {
        user: userInfo,
        role: userInfo?.role ?? "campaign_builder",
        isAdmin: userInfo?.is_admin ?? false,
        canBuild: userInfo?.can_build ?? true,
        isViewer: userInfo?.is_viewer ?? false,
      };

  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useUser() {
  return useContext(UserContext);
}
