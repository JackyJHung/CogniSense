// CogniSense mobile root. Screens: Login, Signup, Dashboard, Morning, Midday, Evening, Report, Suggestions.
import React, { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import LoginScreen from './screens/LoginScreen';
import SignupScreen from './screens/SignupScreen';
import DashboardScreen from './screens/DashboardScreen';
import MorningScreen from './screens/MorningScreen';
import MiddayScreen from './screens/MiddayScreen';
import EveningScreen from './screens/EveningScreen';
import ReportScreen from './screens/ReportScreen';
import SuggestionsScreen from './screens/SuggestionsScreen';
import { loadBackendUrl, loadSession } from './api';

const Stack = createNativeStackNavigator();

export default function App() {
  useEffect(() => {
    // Restore the persisted backend URL and bearer token before any request.
    loadBackendUrl();
    loadSession();
  }, []);

  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Login"
        screenOptions={{
          headerStyle: { backgroundColor: '#4a5568' },
          headerTintColor: '#fff',
        }}
      >
        <Stack.Screen name="Login" component={LoginScreen} options={{ title: 'CogniSense' }} />
        <Stack.Screen name="Signup" component={SignupScreen} options={{ title: 'Create account' }} />
        <Stack.Screen name="Dashboard" component={DashboardScreen} />
        <Stack.Screen name="Morning" component={MorningScreen} options={{ title: 'Morning check-in' }} />
        <Stack.Screen name="Midday" component={MiddayScreen} options={{ title: 'Midday check-in' }} />
        <Stack.Screen name="Evening" component={EveningScreen} options={{ title: 'Evening check-in' }} />
        <Stack.Screen name="Report" component={ReportScreen} options={{ title: 'Risk report' }} />
        <Stack.Screen name="Suggestions" component={SuggestionsScreen} options={{ title: 'Daily suggestions' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
