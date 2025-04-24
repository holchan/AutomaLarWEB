import React, { useState, useEffect } from "react";
import type { FC } from "react"; // Type import

interface GreeterProps {
  initialName?: string;
}

interface ComponentState {
  name: string;
  count: number;
}

class GreeterComponent extends React.Component<GreeterProps, ComponentState> {
  state: ComponentState = {
    name: this.props.initialName || "World",
    count: 0,
  };

  private intervalId: NodeJS.Timeout | null = null;

  componentDidMount() {
    this.intervalId = setInterval(() => {
      this.setState((prevState) => ({ count: prevState.count + 1 }));
    }, 1000);
  }

  componentWillUnmount() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
    }
  }

  render() {
    const { name, count } = this.state;
    return (
      <div>
        <h1>Hello, {name}!</h1>
        <p>Count: {count}</p>
        <button onClick={() => this.setState({ name: "React Developer" })}>
          Change Name
        </button>
      </div>
    );
  }
}

export const FunctionalGreeter: FC<GreeterProps> = ({
  initialName = "Functional World",
}) => {
  const [name, setName] = useState<string>(initialName);
  return <h1>Hi, {name}!</h1>;
};

export default GreeterComponent;
